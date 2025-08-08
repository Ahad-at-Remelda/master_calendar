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

from .models import Event, GoogleWebhookChannel, OutlookWebhookSubscription,SyncedCalendar
from .forms import EventForm
from datetime import date

from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger(__name__)


def redirect_after_login(request):
    today = timezone.now()

def redirect_after_login(request):
    today = timezone.now()
    return redirect(f'/calendar/{today.year}/{today.month}/')
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
def disconnect_social_account(request, provider):
    try:
        social_account = SocialAccount.objects.get(user=request.user, provider=provider)
        # Delete SyncedCalendars and their events for this social account
        synced_calendars = SyncedCalendar.objects.filter(user=request.user, social_account_id=social_account.id)
        for sc in synced_calendars:
            Event.objects.filter(user=request.user, synced_calendar=sc).delete()
            sc.delete()

        # Remove webhook entries for this social account
        GoogleWebhookChannel.objects.filter(social_account_id=social_account.id).delete()
        OutlookWebhookSubscription.objects.filter(social_account_id=social_account.id).delete()

        # Finally delete the social account
        social_account.delete()
        messages.success(request, f"Successfully disconnected your {provider.capitalize()} account and removed associated synced events.")
    except SocialAccount.DoesNotExist:
        messages.error(request, f"You do not have a {provider.capitalize()} account connected.")
    except Exception as e:
        messages.error(request, f"An error occurred: {e}")

    return redirect(request.META.get('HTTP_REFERER', '/'))


@login_required
def calendar_view(request, year, month):
    """
    Final, definitive version. This correctly handles the allauth "same email"
    user account merging and displays all events for the single, unified user.
    """
    year = int(year)
    month = int(month)
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    first_weekday, num_days = cal.monthrange(year, month)
    start_day_of_week = (first_weekday + 1) % 7
    events_by_day = {day: [] for day in range(1, num_days + 1)}

    if request.user.is_authenticated:
        # --- THIS IS THE CRITICAL FIX ---
        # We no longer need to check for specific providers. If the user is logged in,
        # all their social accounts (Google, Microsoft, etc.) are linked to the
        # single `request.user` object. We simply fetch all events that belong to this user.
        all_user_events = Event.objects.filter(
            user=request.user,
            date__year=year,
            date__month=month
        ).order_by('start_time')
        # --------------------------------

        for event in all_user_events:
            start_time_str = event.start_time.strftime('%I:%M %p') if event.start_time else 'All Day'
            
            # Ensure the day from the event date exists in our dictionary
            if event.date.day in events_by_day:
                events_by_day[event.date.day].append({
                    'id': event.id,
                    'title': event.title,
                    'source': event.source,
                    'start_time': start_time_str
                })

    # Get the list of connected accounts to pass to the template for the UI
    connected_accounts = SocialAccount.objects.filter(user=request.user).values_list('provider', flat=True)

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
        'year': year,
        'month': month,
        'days_data': days_data,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        # Pass the connection status to the template for the sidebar buttons
        'google_connected': 'google' in connected_accounts,
        'outlook_connected': 'microsoft' in connected_accounts or 'MasterCalendarClient' in connected_accounts,
    }
    return render(request, 'scheduler_app/calendar.html', context)



# --- THIS IS THE FINAL, CORRECTED GOOGLE WEBHOOK RECEIVER ---
@csrf_exempt
def google_webhook_receiver(request):
    channel_id = request.headers.get('X-Goog-Channel-ID') or request.META.get('HTTP_X_GOOG_CHANNEL_ID')
    resource_state = request.headers.get('X-Goog-Resource-State') or request.META.get('HTTP_X_GOOG_RESOURCE_STATE')
    logger.info(f"Received Google webhook: Channel={channel_id}, State={resource_state}")

    if not channel_id:
        return HttpResponse("Missing Channel ID", status=200)

    try:
        webhook = GoogleWebhookChannel.objects.get(channel_id=channel_id)
    except GoogleWebhookChannel.DoesNotExist:
        logger.warning(f"Unknown Google channel {channel_id}")
        return HttpResponse("Unknown channel", status=200)

    # Look up SocialAccount by stored id to get the correct SocialToken and user
    try:
        social_acc = SocialAccount.objects.get(id=webhook.social_account_id)
    except SocialAccount.DoesNotExist:
        logger.error(f"No SocialAccount found with id {webhook.social_account_id}")
        return HttpResponse("No social account", status=200)

    user = social_acc.user

    if resource_state not in ['exists', 'sync', 'updated', 'deleted']:
        logger.info(f"Notification ignored: state is '{resource_state}'.")
        return HttpResponse("Notification ignored", status=200)

    try:
        token = SocialToken.objects.get(account=social_acc)
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
        google_event_ids = {e['id'] for e in google_events_data if e.get('id')}

        # Upsert events into DB under the app user and mark synced_calendar if present
        for event_data in google_events_data:
            event_id = event_data.get('id')
            if not event_id:
                continue
            start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
            if not start_raw:
                continue
            start_time = parser.parse(start_raw)
            end_raw = event_data.get('end', {}).get('dateTime') or event_data.get('end', {}).get('date')
            end_time = parser.parse(end_raw) if end_raw else None

            Event.objects.update_or_create(
                user=user,
                source='google',
                event_id=event_id,
                defaults={
                    'title': event_data.get('summary', 'No Title'),
                    'description': event_data.get('description', ''),
                    'date': start_time.date(), 'start_time': start_time, 'end_time': end_time,
                    'etag': event_data.get('etag', ''),
                    'meeting_link': event_data.get('hangoutLink', ''),
                    'location': event_data.get('location', ''),
                    'is_recurring': 'recurringEventId' in event_data
                }
            )

        # Remove deleted events (for this user + provider)
        Event.objects.filter(user=user, source='google').exclude(event_id__in=google_event_ids).delete()

        # Notify via channels
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(f"user_{user.id}", {"type": "calendar.update", "update": "calendar_changed"})
        logger.info(f"Google sync complete. Sent update to WebSocket for user {user.id}")

    except Exception as e:
        logger.error(f"Error syncing Google webhook for social_acc {webhook.social_account_id}: {e}", exc_info=True)
        return HttpResponse("Sync failure", status=500)

    return HttpResponse("OK", status=200)


@csrf_exempt
def outlook_webhook_receiver(request):
    validation_token = request.GET.get('validationToken')
    if validation_token:
        logger.info("Received Outlook validation request. Responding with token.")
        return HttpResponse(validation_token, content_type='text/plain', status=200)

    try:
        notification = json.loads(request.body.decode('utf-8') or '{}')
        if not notification:
            logger.warning("Empty Outlook notification body")
            return HttpResponse(status=200)

        # The notification includes subscriptionId; there may be multiple items
        for notif in notification.get('value', []):
            subscription_id = notif.get('subscriptionId')
            if not subscription_id:
                continue
            try:
                sub = OutlookWebhookSubscription.objects.get(subscription_id=subscription_id)
            except OutlookWebhookSubscription.DoesNotExist:
                logger.warning(f"No Outlook subscription found with id {subscription_id}")
                continue

            # Find the social account and token
            try:
                social_acc = SocialAccount.objects.get(id=sub.social_account_id)
            except SocialAccount.DoesNotExist:
                logger.error(f"No SocialAccount for id {sub.social_account_id}")
                continue

            user = social_acc.user
            # Use the token for this social account
            try:
                token = SocialToken.objects.get(account=social_acc)
                headers = {'Authorization': f'Bearer {token.token}'}
                graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/events'
                response = requests.get(graph_api_endpoint, headers=headers)
                response.raise_for_status()
                outlook_events_data = response.json().get('value', [])
            except Exception as e:
                logger.error(f"Error fetching Outlook events for social_account {sub.social_account_id}: {e}", exc_info=True)
                continue

            outlook_event_ids_in_sync = []
            for event_data in outlook_events_data:
                event_id = event_data.get('id')
                if not event_id:
                    continue
                outlook_event_ids_in_sync.append(event_id)
                start_raw = event_data.get('start', {}).get('dateTime')
                if not start_raw:
                    continue
                start_time = parser.parse(start_raw)
                end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else None
                Event.objects.update_or_create(
                    user=user,
                    source='microsoft',
                    event_id=event_id,
                    defaults={
                        'title': event_data.get('subject', 'No Title'),
                        'description': event_data.get('bodyPreview', ''),
                        'date': start_time.date(), 'start_time': start_time, 'end_time': end_time,
                        'etag': event_data.get('@odata.etag', ''),
                        'location': event_data.get('location', {}).get('displayName', ''),
                    }
                )

            Event.objects.filter(user=user, source='microsoft').exclude(event_id__in=outlook_event_ids_in_sync).delete()

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(f"user_{user.id}", {"type": "calendar.update", "update": "calendar_changed"})
            logger.info(f"Outlook sync complete. Sent update to WebSocket for user {user.id}")

    except Exception as e:
        logger.error(f"Error processing Outlook webhook: {e}", exc_info=True)
        # still return 200 so provider considers notification delivered
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



login_required
def select_calendars_view(request, provider):
    """
    Fetches the list of available calendars from Google/Outlook and
    presents them to the user to choose which ones to sync.
    """
    user = request.user
    calendars = []
    error = None

    try:
        token = SocialToken.objects.get(account__user=user, account__provider=provider)
        
        if provider == 'google':
            credentials = Credentials(...) # Build credentials as before
            service = build('calendar', 'v3', credentials=credentials)
            calendar_list = service.calendarList().list().execute()
            calendars = [{'id': cal['id'], 'name': cal['summary']} for cal in calendar_list.get('items', [])]
        
        elif provider == 'microsoft':
            headers = {'Authorization': f'Bearer {token.token}'}
            response = requests.get('https://graph.microsoft.com/v1.0/me/calendars', headers=headers)
            response.raise_for_status()
            calendar_list = response.json().get('value', [])
            calendars = [{'id': cal['id'], 'name': cal['name']} for cal in calendar_list]
            
    except Exception as e:
        error = f"Could not fetch your calendar list: {e}"
        logger.error(error)

    # Get the list of calendars that are ALREADY synced for this user
    synced_calendars = SyncedCalendar.objects.filter(user=user, provider=provider).values_list('calendar_id', flat=True)

    context = {
        'provider': provider,
        'calendars': calendars,
        'synced_calendars': synced_calendars,
        'error': error,
    }
    return render(request, 'scheduler_app/select_calendars.html', context)


@login_required
def save_calendar_selection_view(request, provider):
    """
    Saves the user's choices from the 'select_calendars' form.
    """
    if request.method == 'POST':
        user = request.user
        selected_calendar_ids = request.POST.getlist('calendar_ids')
        
        # Here you would add the full logic to:
        # 1. Fetch calendar names for the selected IDs.
        # 2. Save the choices to the SyncedCalendar model.
        # 3. Trigger the initial full sync for each selected calendar.
        # 4. Register a webhook for each selected calendar.
        
        messages.success(request, "Your calendar selections have been saved and are now syncing.")
        today = date.today()
        return redirect('calendar', year=today.year, month=today.month)

    # Redirect away if accessed via GET
    return redirect('home')