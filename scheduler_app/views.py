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

# (home, add_event, and calendar_view are all correct from your last version, no changes needed there)
def home(request):
    today = date.today()
    context = {'year': today.year, 'month': today.month}
    return render(request, 'scheduler_app/home.html', context)

@login_required
def add_event(request, year, month, day):
    event_date = datetime.date(year, month, day)
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.user = request.user
            event.date = event_date
            event.save()
            return redirect('calendar', year=year, month=month)
    else:
        form = EventForm(initial={'date': event_date})
    context = {'form': form, 'year': year, 'month': month}
    return render(request, 'scheduler_app/add_event.html', context)

def calendar_view(request, year, month):
    # This entire view is correct from your previous file.
    # No changes are needed.
    year = int(year)
    month = int(month)
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    first_weekday, num_days = cal.monthrange(year, month)
    start_day_of_week = (first_weekday + 1) % 7
    events_by_day = {day: [] for day in range(1, num_days + 1)}
    google_connected = False

    if request.user.is_authenticated:
        local_events = Event.objects.filter(user=request.user, date__year=year, date__month=month)
        try:
            token = SocialToken.objects.get(account__user=request.user, account__provider='google')
            google_connected = True
            credentials = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                token.token = credentials.token
                token.save()
            service = build('calendar', 'v3', credentials=credentials)
            time_min = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc).isoformat()
            time_max = datetime.datetime(year, month, num_days, 23, 59, 59, tzinfo=datetime.timezone.utc).isoformat()
            events_result = service.events().list(calendarId='primary', timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
            google_events = events_result.get('items', [])
            for event in google_events:
                start_info = event.get('start', {})
                date_str = start_info.get('dateTime', start_info.get('date'))
                if not date_str: continue
                start_datetime = parser.parse(date_str)
                day = start_datetime.day
                if 1 <= day <= num_days:
                    events_by_day[day].append({'title': event.get('summary', 'No Title'), 'start_time': start_datetime.strftime('%I:%M %p') if 'dateTime' in start_info else 'All Day', 'source': 'google'})
        except SocialToken.DoesNotExist:
            logger.info("No Google token found. Skipping Google Calendar sync.")
        except Exception as e:
            logger.error(f"Google Calendar sync failed: {e}", exc_info=True)
            messages.error(request, "An error occurred while syncing with Google Calendar.")
    else:
        local_events = Event.objects.filter(user__isnull=True, date__year=year, date__month=month)
    
    for event in local_events:
        events_by_day[event.date.day].append({'title': event.title, 'source': 'local', 'start_time': event.date.strftime('%I:%M %p')})

    days_data = []
    for _ in range(start_day_of_week):
        days_data.append({'is_placeholder': True})
    for day in range(1, num_days + 1):
        days_data.append({'day': day, 'events': sorted(events_by_day.get(day, []), key=lambda x: x['title']), 'is_placeholder': False})

    context = {
        'year': year, 'month': month, 'days_data': days_data,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'google_connected': google_connected
    }
    return render(request, 'scheduler_app/calendar.html', context)

# --- This is the view that receives the webhook from Google ---
@csrf_exempt
def google_webhook_receiver(request):
    channel_id = request.headers.get('X-Goog-Channel-ID')
    resource_state = request.headers.get('X-Goog-Resource-State')

    # Print raw headers and body for debugging
    print("🔔 Webhook Headers:")
    for k, v in request.headers.items():
        print(f"{k}: {v}")
    print("🔔 Webhook Raw Body:")
    print(request.body.decode("utf-8"))

    logger.info(f"Webhook Headers: {dict(request.headers)}")
    logger.info(f"Webhook Body: {request.body.decode('utf-8')}")
    print("🔔 Webhook Raw Body:")
    print(request.body.decode("utf-8"))
    if resource_state in ['sync', 'exists']:
        logger.info(f"Received Google Webhook notification for channel: {channel_id}")
        try:
            webhook_channel = GoogleWebhookChannel.objects.get(channel_id=channel_id)
            user_id = webhook_channel.user.id

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{user_id}",
                {
                    "type": "calendar.update",
                    "update": "calendar_changed"
                }
            )
            logger.info(f"Sent calendar update to WebSocket group: user_{user_id}")

        except GoogleWebhookChannel.DoesNotExist:
            logger.error(f"Received webhook for unknown channel_id: {channel_id}")

    return HttpResponse(status=200)



def start_google_calendar_watch(user, credentials):
    service = build('calendar', 'v3', credentials=credentials)

    channel_id = str(uuid.uuid4())
    webhook_url = "https://79c15e1980a4.ngrok-free.app/google-webhook/"  

    body = {
    "id": channel_id,
    "type": "web_hook",
    "address": webhook_url,
    "token": "some_random_token_123",  # Optional
    "params": {
        "ttl": "604800"  # 7 days in seconds
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
