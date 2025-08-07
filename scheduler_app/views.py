# scheduler_app/views.py


from django.conf import settings

# scheduler_app/views.py

import datetime
import calendar as cal
import logging
import uuid
import requests
import json
from django.contrib.auth.models import User

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from allauth.socialaccount.models import SocialToken,SocialAccount
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from dateutil import parser
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Event, GoogleWebhookChannel, OutlookWebhookSubscription
from .forms import EventForm
from datetime import date

logger = logging.getLogger(__name__)

def home(request):
    today = date.today()
    context = {'year': today.year, 'month': today.month}
    return render(request, 'scheduler_app/home.html', context)

@login_required
def add_event(request):
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
    today = date.today()
    context = {'form': form, 'year': today.year, 'month': today.month}
    return render(request, 'scheduler_app/add_event.html', context)

@login_required
def calendar_view(request, year, month):
    """
    Final, correct version. Displays events from the local DB based on
    which social accounts the user has connected.
    """
    year = int(year)
    month = int(month)
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    first_weekday, num_days = cal.monthrange(year, month)
    start_day_of_week = (first_weekday + 1) % 7
    events_by_day = {day: [] for day in range(1, num_days + 1)}

    if request.user.is_authenticated:
        # Determine which social accounts are connected for this user
        connected_accounts = SocialAccount.objects.filter(user=request.user).values_list('provider', flat=True)
        
        sources_to_fetch = ['local']
        if 'google' in connected_accounts:
            sources_to_fetch.append('google')
        if 'MasterCalendarClient' in connected_accounts:
            sources_to_fetch.append('outlook')

        # Fetch all events from the database that match the user and their connected sources.
        all_user_events = Event.objects.filter(
            user=request.user,
            source__in=sources_to_fetch,
            date__year=year,
            date__month=month
        ).order_by('start_time')

        for event in all_user_events:
            start_time_str = event.start_time.strftime('%I:%M %p') if event.start_time else 'All Day'
            events_by_day[event.date.day].append({
                'id': event.id,
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



# --- THIS IS THE FINAL, CORRECTED GOOGLE WEBHOOK RECEIVER ---
@csrf_exempt
def google_webhook_receiver(request):
    """
    This view is now more robust and guarantees it always returns an HttpResponse.
    """
    channel_id = request.headers.get('X-Goog-Channel-ID')
    resource_state = request.headers.get('X-Goog-Resource-State')
    logger.info(f"Received Google webhook: Channel={channel_id}, State={resource_state}")

    if not channel_id:
        return HttpResponse("Notification ignored: Missing Channel ID.", status=200)

    try:
        webhook = GoogleWebhookChannel.objects.get(channel_id=channel_id)
        user = webhook.user
    except GoogleWebhookChannel.DoesNotExist:
        logger.warning(f"Received webhook for an unknown channel_id: {channel_id}")
        return HttpResponse("Unknown channel ID", status=200)

    if resource_state not in ['exists', 'sync']:
        logger.info(f"Notification ignored: state is '{resource_state}'.")
        return HttpResponse("Notification ignored: state is not 'exists' or 'sync'.", status=200)

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
        events_result = service.events().list(calendarId='primary', singleEvents=True).execute()
        google_events_data = events_result.get('items', [])
        
        google_event_ids = {event_data['id'] for event_data in google_events_data}

        for event_data in google_events_data:
            event_id = event_data.get('id')
            if not event_id: continue
            start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
            if not start_raw: continue
            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime') or event_data.get('end', {}).get('date')) if event_data.get('end') else None
            Event.objects.update_or_create(
                user=user, event_id=event_id,
                defaults={
                    'title': event_data.get('summary', 'No Title'),
                    'description': event_data.get('description', ''),
                    'date': start_time.date(), 'start_time': start_time, 'end_time': end_time,
                    'source': 'google', 'etag': event_data.get('etag', ''),
                    'meeting_link': event_data.get('hangoutLink', ''),
                    'location': event_data.get('location', ''),
                    'is_recurring': 'recurringEventId' in event_data
                }
            )
        
        Event.objects.filter(user=user, source='google').exclude(event_id__in=google_event_ids).delete()

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(f"user_{user.id}", {"type": "calendar.update", "update": "calendar_changed"})
        logger.info(f"Sync complete. Sent update to WebSocket for user {user.id}")

    except Exception as e:
        logger.error(f"Error syncing events for {user.username} via webhook: {e}", exc_info=True)
        return HttpResponse("Sync failure", status=500)

    return HttpResponse("Webhook processed successfully.", status=200)

@csrf_exempt
def outlook_webhook_receiver(request):
    # (This view is correct and needs no changes)
    print("Received Outlook entry request")
    validation_token = request.GET.get('validationToken')
    if validation_token:
        logger.info("Received Outlook validation request. Responding with token.")
        return HttpResponse(validation_token, content_type='text/plain', status=200)
    try:
        notification = json.loads(request.body)
        print(f"Received Outlook notification: {notification}")
        subscription_id = notification['value'][0]['subscriptionId']
        logger.info(f"Received Outlook Webhook notification for subscription: {subscription_id}")
        webhook_subscription = get_object_or_404(OutlookWebhookSubscription, subscription_id=subscription_id)
        user = webhook_subscription.user
        print(f"User for subscription {subscription_id}: {user.username}")
        token = SocialToken.objects.get(account__user=user, account__provider='MasterCalendarClient')
        print(f"Token for user {user.username}: {token.token}")
        headers = {'Authorization': f'Bearer {token.token}'}
        graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/events'
        response = requests.get(graph_api_endpoint, headers=headers)
        response.raise_for_status()
        outlook_events_data = response.json().get('value', [])
        logger.info(f"Fetched {len(outlook_events_data)} total events from Outlook for user {user.username} after webhook.")
        outlook_event_ids_in_sync = []
        for event_data in outlook_events_data:
            event_id = event_data.get('id')
            if not event_id: continue
            outlook_event_ids_in_sync.append(event_id)
            start_raw = event_data.get('start', {}).get('dateTime')
            if not start_raw: continue
            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else None
            Event.objects.update_or_create(
                user=user, event_id=event_id,
                defaults={
                    'title': event_data.get('subject', 'No Title'),
                    'description': event_data.get('bodyPreview', ''),
                    'date': start_time.date(), 'start_time': start_time, 'end_time': end_time,
                    'source': 'outlook', 'etag': event_data.get('@odata.etag', ''),
                    'location': event_data.get('location', {}).get('displayName', ''),
                }
            )
        Event.objects.filter(user=user, source='outlook').exclude(event_id__in=outlook_event_ids_in_sync).delete()
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(f"user_{user.id}", {"type": "calendar.update", "update": "calendar_changed"})
        logger.info(f"Outlook sync complete. Sent update to WebSocket for user {user.id}")
    except Exception as e:
        logger.error(f"Error processing Outlook webhook: {e}", exc_info=True)
    return HttpResponse(status=200)




@login_required
def event_detail_api(request, event_id):
    """
    API endpoint that returns the details of a single event as JSON.
    This is called by the JavaScript when an event is clicked on the calendar.
    """
    # Find the event by its unique database ID, ensuring it belongs to the
    # currently logged-in user for security. If not found, it will raise a 404 error.
    event = get_object_or_404(Event, id=event_id, user=request.user)

    # Format the start and end times into a more human-readable string.
    # Handle the case where an event might be "all-day" and not have a specific time.
    start_time = event.start_time.strftime('%A, %B %d, %Y at %I:%M %p') if event.start_time else "All-day"
    end_time = event.end_time.strftime('%A, %B %d, %Y at %I:%M %p') if event.end_time else ""

    # Prepare all the event's data in a dictionary to be sent as JSON.
    data = {
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'date': event.date.strftime('%Y-%m-%d'),
        'start_time': start_time,
        'end_time': end_time,
        'location': event.location,
        'meeting_link': event.meeting_link,
        'source': event.source or 'local', # Ensure the source is not None for the template
    }
    
    return JsonResponse(data)



# The following views are not strictly necessary for production but can be useful for debugging or testing.
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


# @login_required
# def event_detail_api(request, event_id):
#     """
#     This is an API endpoint that returns the details of a single event as JSON.
#     """
#     # Find the event by its ID, ensuring it belongs to the logged-in user for security.
#     event = get_object_or_404(Event, id=event_id, user=request.user)

#     # Format the start and end times for display
#     start_time = event.start_time.strftime('%A, %B %d, %Y at %I:%M %p') if event.start_time else "All-day"
#     end_time = event.end_time.strftime('%A, %B %d, %Y at %I:%M %p') if event.end_time else ""

#     # Prepare the data to be sent as JSON
#     data = {
#         'id': event.id,
#         'title': event.title,
#         'description': event.description,
#         'date': event.date.strftime('%Y-%m-%d'),
#         'start_time': start_time,
#         'end_time': end_time,
#         'location': event.location,
#         'meeting_link': event.meeting_link,
#         'source': event.source,
#     }
#     return JsonResponse(data)

@login_required
def sync_outlook_events(request):
    try:
        token = SocialToken.objects.get(account__user=request.user, account__provider='microsoft')
        headers = {'Authorization': f'Bearer {token.token}'}
        graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/events'
        response = requests.get(graph_api_endpoint, headers=headers)
        response.raise_for_status()
        outlook_events_data = response.json().get('value', [])

        for event_data in outlook_events_data:
            event_id = event_data.get('id')
            if not event_id:
                continue

            start_raw = event_data.get('start', {}).get('dateTime')
            if not start_raw:
                continue

            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else None

            Event.objects.update_or_create(
                user=request.user,
                event_id=event_id,
                defaults={
                    'title': event_data.get('subject', 'No Title'),
                    'description': event_data.get('bodyPreview', ''),
                    'date': start_time.date(),
                    'start_time': start_time,
                    'end_time': end_time,
                    'source': 'outlook',
                    'etag': event_data.get('@odata.etag', ''),
                    'location': event_data.get('location', {}).get('displayName', ''),
                }
            )

        return JsonResponse({'status': 'success', 'count': len(outlook_events_data)})
    except Exception as e:
        logger.error(f"Manual Outlook sync failed: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



# # views.py
# import requests
# import logging
# from allauth.socialaccount.models import SocialToken
# from django.contrib.auth.decorators import login_required
# from django.http import JsonResponse

# # Set up logger
# logger = logging.getLogger(__name__)

@login_required
def sync_outlook(request):
    user = request.user

    logger.info("🔔 Received request to sync Outlook for user: %s", user.username)

    try:
        token = SocialToken.objects.get(account__user=user, account__provider='microsoft')
        access_token = token.token
        logger.info("✅ Access token retrieved: %s", access_token)

    except SocialToken.DoesNotExist:
        logger.error("❌ No SocialToken found for user: %s", user.username)
        return JsonResponse({'status': 'error', 'message': 'SocialToken matching query does not exist.'})

    # Request to Microsoft Graph API to get calendar events
    graph_url = "https://graph.microsoft.com/v1.0/me/events"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json'
    }

    logger.info("📤 Sending request to Microsoft Graph API: %s", graph_url)
    logger.debug("📨 Request headers: %s", headers)

    response = requests.get(graph_url, headers=headers)

    logger.info("📥 Received response status: %s", response.status_code)
    logger.debug("📦 Response content: %s", response.text)

    if response.status_code == 200:
        events = response.json().get('value', [])
        logger.info("✅ Events fetched successfully: %d events found", len(events))
        return JsonResponse({'status': 'success', 'events': events})

    logger.error("❌ Failed to fetch events from Microsoft Graph: %s", response.text)
    return JsonResponse({'status': 'error', 'message': 'Failed to fetch events', 'details': response.text})
