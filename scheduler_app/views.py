# scheduler_app/views.py


import datetime
import calendar as cal
import logging
import uuid

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from allauth.socialaccount.models import SocialToken
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from dateutil import parser
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Event, GoogleWebhookChannel
from .forms import EventForm
from datetime import date

logger = logging.getLogger(__name__)

def home(request):
    today = date.today()
    context = {'year': today.year, 'month': today.month}
    return render(request, 'scheduler_app/home.html', context)

@login_required
def add_event(request):
    """
    This view handles adding a new event via a generalized form.
    It now passes the current date to the template for the cancel button.
    """
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.user = request.user
            event.source = 'local'
            event.save()
            
            new_event_date = form.cleaned_data['date']
            return redirect('calendar', year=new_event_date.year, month=new_event_date.month)
    else:
        form = EventForm(initial={'date': date.today()})

    # --- THIS IS THE CRITICAL FIX ---
    # We will pass the current year and month to the template context
    # so the "Cancel" button knows where to go.
    today = date.today()
    context = {
        'form': form,
        'year': today.year,
        'month': today.month
    }
    # --------------------------------
    return render(request, 'scheduler_app/add_event.html', context)


@login_required
def calendar_view(request, year, month):
    """
    This view is now efficient and only displays events from the local database.
    This solves the event duplication problem.
    """
    year = int(year)
    month = int(month)
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    first_weekday, num_days = cal.monthrange(year, month)
    start_day_of_week = (first_weekday + 1) % 7
    events_by_day = {day: [] for day in range(1, num_days + 1)}

    if request.user.is_authenticated:
        # Fetch all events (local and synced) for this user from our one database table
        all_user_events = Event.objects.filter(
            user=request.user,
            date__year=year,
            date__month=month
        ).order_by('start_time')

        for event in all_user_events:
            start_time_str = event.start_time.strftime('%I:%M %p') if event.start_time else 'All Day'
            events_by_day[event.date.day].append({
                'title': event.title,
                'source': event.source,
                'start_time': start_time_str
            })

    days_data = []
    for _ in range(start_day_of_week):
        days_data.append({'is_placeholder': True})
    for day in range(1, num_days + 1):
        days_data.append({
            'day': day,
            'events': events_by_day.get(day, []),
            'is_placeholder': False
        })

    context = {
        'year': year, 'month': month, 'days_data': days_data,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
    }
    return render(request, 'scheduler_app/calendar.html', context)


@csrf_exempt
def google_webhook_receiver(request):
    """
    Receives notifications, syncs the DB, and triggers the WebSocket push.
    """
    channel_id = request.headers.get('X-Goog-Channel-ID')
    resource_id = request.headers.get('X-Goog-Resource-ID')
    logger.info(f"Received Google webhook: Channel={channel_id}, Resource={resource_id}")

    try:
        webhook = GoogleWebhookChannel.objects.get(channel_id=channel_id)
        user = webhook.user
    except GoogleWebhookChannel.DoesNotExist:
        return HttpResponse("Unknown channel ID", status=404)

    try:
        token = SocialToken.objects.get(account__user=user, account__provider='google')
        credentials = Credentials(
            token=token.token, refresh_token=token.token_secret,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=token.app.client_id, client_secret=token.app.secret
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token.token = credentials.token
            token.save()

        service = build('calendar', 'v3', credentials=credentials)
        events_result = service.events().list(calendarId='primary', singleEvents=True, orderBy='startTime').execute()
        google_events = events_result.get('items', [])
        logger.info(f"Fetched {len(google_events)} total events from Google for user {user.username} after webhook.")

        google_event_ids_in_sync = []
        for event_data in google_events:
            event_id = event_data.get('id')
            if not event_id: continue
            google_event_ids_in_sync.append(event_id)
            
            start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
            if not start_raw: continue

            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime') or event_data.get('end', {}).get('date')) if event_data.get('end') else None

            Event.objects.update_or_create(
                user=user, event_id=event_id,
                defaults={
                    'title': event_data.get('summary', 'No Title'),
                    'description': event_data.get('description', ''),
                    'date': start_time.date(),
                    'start_time': start_time,
                    'end_time': end_time,
                    'source': 'google',
                    'etag': event_data.get('etag', ''),
                    'meeting_link': event_data.get('hangoutLink', ''),
                    'location': event_data.get('location', ''),
                    'is_recurring': 'recurringEventId' in event_data
                }
            )
        
        Event.objects.filter(user=user, source='google').exclude(event_id__in=google_event_ids_in_sync).delete()

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user.id}",
            {"type": "calendar.update", "update": "calendar_changed"}
        )
        logger.info(f"Sync complete. Sent update to WebSocket for user {user.id}")

    except Exception as e:
        logger.error(f"Error syncing events for {user.username} via webhook: {e}", exc_info=True)
        return HttpResponse("Sync failure", status=500)

    return HttpResponse("Webhook processed successfully.", status=200)

# The other helper/debug views are not needed for production but can be kept for testing
# ... (start_google_calendar_watch, trigger_webhook, sync_events) ...
def start_google_calendar_watch(user, credentials):
    service = build('calendar', 'v3', credentials=credentials)
    channel_id = str(uuid.uuid4())
    webhook_url = "https://79c15e1980a4.ngrok-free.app/google-webhook/"

    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": webhook_url,
        "token": "some_random_token_123",
        "params": {
            "ttl": "604800"
        }
    }

    response = service.events().watch(calendarId='primary', body=body).execute()

    GoogleWebhookChannel.objects.update_or_create(
        user=user,
        defaults={
            'channel_id': channel_id,
            'resource_id': response.get("resourceId"),
            'expiration': datetime.datetime.fromtimestamp(int(response["expiration"]) / 1000.0),
        }
    )

    logger.info(f"Google Calendar watch started for user {user.username}")


@login_required
def trigger_webhook(request):
    from scheduler_app.signals import setup_google_webhook_on_login
    from allauth.socialaccount.models import SocialAccount

    try:
        account = SocialAccount.objects.get(user=request.user, provider='google')
        setup_google_webhook_on_login(sender=None, request=request, sociallogin=type('obj', (object,), {
            'user': request.user,
            'token': account.socialtoken_set.first(),
            'account': account
        })())
        return HttpResponse("✅ Webhook manually triggered.")
    except Exception as e:
        return HttpResponse(f"❌ Failed to trigger webhook: {e}", status=500)


@login_required
def sync_events(request):
    try:
        token = SocialToken.objects.get(account__user=request.user, account__provider='google')
        credentials = Credentials(
            token=token.token,
            refresh_token=token.token_secret,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=token.app.client_id,
            client_secret=token.app.secret
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token.token = credentials.token
            token.save()

        service = build('calendar', 'v3', credentials=credentials)
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        for event in events_result.get('items', []):
            event_id = event.get('id')
            summary = event.get('summary', '')
            description = event.get('description', '')
            start_time = event['start'].get('dateTime') or event['start'].get('date')
            end_time = event['end'].get('dateTime') or event['end'].get('date')

            Event.objects.update_or_create(
                google_event_id=event_id,
                user=request.user,
                defaults={
                    'title': summary,
                    'description': description,
                    'start_time': start_time,
                    'end_time': end_time,
                    'date': start_time.date(),  

                }
            )

        return JsonResponse({'status': 'success'})
    except Exception as e:
        logger.error(f"Manual sync failed: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
