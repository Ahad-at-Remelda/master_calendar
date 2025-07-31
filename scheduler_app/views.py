# scheduler_app/views.py

import datetime
import calendar as cal
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache

from allauth.socialaccount.models import SocialToken
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from dateutil import parser

from .models import Event, GoogleWebhookChannel
from .forms import EventForm

logger = logging.getLogger(__name__)

def home(request):
    # (This view is correct, no changes needed)
    current_date = datetime.date.today()
    context = {'year': current_date.year, 'month': current_date.month}
    return render(request, 'scheduler_app/home.html', context)

@login_required
def add_event(request, year, month, day):
    # (This view is correct, no changes needed)
    event_date = datetime.date(year, month, day)
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.date = event_date
            event.save()
            return redirect('calendar', year=year, month=month)
    else:
        form = EventForm(initial={'date': event_date})
    context = {'form': form, 'year': year, 'month': month}
    return render(request, 'scheduler_app/add_event.html', context)

@login_required
def calendar_view(request, year, month):
    year = int(year)
    month = int(month)
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    first_weekday, num_days = cal.monthrange(year, month)
    start_day_of_week = (first_weekday + 1) % 7
    events_by_day = {day: [] for day in range(1, num_days + 1)}

    local_events = Event.objects.filter(date__year=year, date__month=month)
    for event in local_events:
        events_by_day[event.date.day].append({'title': event.title, 'source': 'local', 'start_time': event.date.strftime('%I:%M %p')})

    try:
        token = SocialToken.objects.get(account__user=request.user, account__provider='google')
        logger.info(f"Found Google token for user: {request.user.username}")
        credentials = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
        
        if credentials.expired and credentials.refresh_token:
            logger.info("Google token is expired, attempting to refresh")
            credentials.refresh(Request())
            token.token = credentials.token
            token.save()
            logger.info("Google token refreshed successfully")

        service = build('calendar', 'v3', credentials=credentials)
        time_min = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc).isoformat()
        time_max = datetime.datetime(year, month, num_days, 23, 59, 59, tzinfo=datetime.timezone.utc).isoformat()
        
        events_result = service.events().list(calendarId='primary', timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
        google_events = events_result.get('items', [])
        logger.info(f"Found {len(google_events)} Google events")

        for event in google_events:
            start_info = event.get('start', {})
            date_str = start_info.get('dateTime', start_info.get('date'))
            if not date_str: continue
            start_datetime = parser.parse(date_str)
            day = start_datetime.day
            if 1 <= day <= num_days:
                events_by_day[day].append({'title': event.get('summary', 'No Title'), 'start_time': start_datetime.strftime('%I:%M %p') if 'dateTime' in start_info else 'All Day', 'source': 'google'})

    except SocialToken.DoesNotExist:
        logger.info(f"No Google token for user '{request.user.username}'. Skipping Google sync.")
    except Exception as e:
        logger.error(f"Google Calendar sync failed: {e}", exc_info=True)
        messages.error(request, "An error occurred while syncing with Google Calendar.")

    days_data = []
    for _ in range(start_day_of_week):
        days_data.append({'is_placeholder': True})
    for day in range(1, num_days + 1):
        days_data.append({'day': day, 'events': sorted(events_by_day.get(day, []), key=lambda x: x['title']), 'is_placeholder': False})

    context = {'year': year, 'month': month, 'days_data': days_data, 'prev_year': prev_year, 'prev_month': prev_month, 'next_year': next_year, 'next_month': next_month}
    return render(request, 'scheduler_app/calendar.html', context)

@csrf_exempt
def google_webhook_receiver(request):
    # (This view is correct, no changes needed)
    channel_id = request.headers.get('X-Goog-Channel-ID')
    resource_state = request.headers.get('X-Goog-Resource-State')
    if resource_state == 'sync' or resource_state == 'exists':
        logger.info(f"Received Google Webhook notification for channel: {channel_id}")
        try:
            webhook_channel = GoogleWebhookChannel.objects.get(channel_id=channel_id)
            user_id = webhook_channel.user.id
            cache.set(f'calendar_updated_{user_id}', True, timeout=120)
            logger.info(f"Set update flag for user_id: {user_id}")
        except GoogleWebhookChannel.DoesNotExist:
            logger.error(f"Received webhook for an unknown channel_id: {channel_id}")
    return HttpResponse(status=200)

@login_required
def check_for_updates(request):
    # (This view is correct, no changes needed)
    user_id = request.user.id
    if cache.get(f'calendar_updated_{user_id}'):
        cache.delete(f'calendar_updated_{user_id}')
        return JsonResponse({'update_available': True})
    return JsonResponse({'update_available': False})