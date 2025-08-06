# scheduler_app/views.py



import requests # We'll use the requests library for the Microsoft Graph API

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
import json

logger = logging.getLogger(__name__)

def home(request):
    today = date.today()
    context = {'year': today.year, 'month': today.month}
    return render(request, 'scheduler_app/home.html', context)

@login_required
def add_event(request):
    """
    This view now correctly handles and displays validation errors from the form.
    """
    if request.method == 'POST':
        form = EventForm(request.POST)
        # --- THIS IS THE CRITICAL CHANGE ---
        # The form.is_valid() call automatically triggers the clean() method.
        # If clean() raises a ValidationError, is_valid() will be False,
        # and the form object will now contain the error messages.
        if form.is_valid():
            event = form.save(commit=False)
            event.user = request.user
            event.source = 'local'
            event.save()
            
            new_event_date = form.cleaned_data['date']
            return redirect('calendar', year=new_event_date.year, month=new_event_date.month)
        # If the form is NOT valid, the code will now fall through and re-render
        # the page, passing the form object (which now contains the errors)
        # to the template. The template will then display them.
            
    else:
        form = EventForm(initial={'date': date.today()})

    today = date.today()
    context = {
        'form': form,
        'year': today.year,
        'month': today.month
    }
    return render(request, 'scheduler_app/add_event.html', context)



@login_required
def calendar_view(request, year, month):
    year = int(year)
    month = int(month)
    # (Navigation and calendar setup logic is correct)
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    first_weekday, num_days = cal.monthrange(year, month)
    start_day_of_week = (first_weekday + 1) % 7
    events_by_day = {day: [] for day in range(1, num_days + 1)}

    if request.user.is_authenticated:
        # Fetch all local events for this user from our database.
        # This will include events synced from both Google and Outlook.
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

    # --- THIS IS THE EXISTING, CORRECT GOOGLE SYNC LOGIC ---
    # We will now add a parallel block for Outlook sync
    try:
        # This is a simplified fetch to ensure the page loads, the real sync happens via webhook
        pass # The webhook handles the main Google Sync
    except Exception as e:
        logger.error(f"Error during Google sync check: {e}")


    # --- THIS IS THE NEW BLOCK FOR OUTLOOK/MICROSOFT GRAPH SYNC ---
    try:
        # 1. Find the user's token for the 'microsoft' provider
        token = SocialToken.objects.get(account__user=request.user, account__provider='microsoft')
        
        # 2. Prepare the request to the Microsoft Graph API
        graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/calendar/events'
        headers = {
            'Authorization': f'Bearer {token.token}',
            'Content-Type': 'application/json'
        }
        
        # Define the time window for the calendar view
        time_min = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
        time_max = datetime.datetime(year, month, num_days, 23, 59, 59, tzinfo=datetime.timezone.utc)
        
        params = {
            '$select': 'subject,start,end,bodyPreview,location',
            '$filter': f"start/dateTime ge '{time_min.isoformat()}' and end/dateTime le '{time_max.isoformat()}'",
            '$orderby': 'start/dateTime'
        }

        # 3. Make the API call
        response = requests.get(graph_api_endpoint, headers=headers, params=params)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        outlook_events_data = response.json().get('value', [])
        logger.info(f"Fetched {len(outlook_events_data)} Outlook events for user {request.user.username}")

        # 4. Process the events and add them to our display dictionary
        for event_data in outlook_events_data:
            start_raw = event_data.get('start', {}).get('dateTime')
            if not start_raw: continue

            start_datetime = parser.parse(start_raw)
            day = start_datetime.day

            if 1 <= day <= num_days:
                events_by_day[day].append({
                    'title': event_data.get('subject', 'No Title'),
                    'source': 'outlook',
                    'start_time': start_datetime.strftime('%I:%M %p')
                })

    except SocialToken.DoesNotExist:
        # This is normal if the user hasn't connected their Outlook account
        pass
    except Exception as e:
        logger.error(f"Outlook Calendar sync failed: {e}", exc_info=True)
        messages.error(request, "An error occurred while syncing with your Outlook Calendar.")
    # ----------------------------------------------------------------

    days_data = []
    for _ in range(start_day_of_week):
        days_data.append({'is_placeholder': True})
    for day in range(1, num_days + 1):
        # We re-sort here to combine events from all sources correctly
        sorted_events = sorted(events_by_day.get(day, []), key=lambda x: x['start_time'])
        days_data.append({
            'day': day,
            'events': sorted_events,
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
    This view now performs a full, intelligent sync.
    - It updates existing events.
    - It creates new events.
    - It deletes events that have been removed from Google Calendar.
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
        
        # Fetch all events from the user's primary calendar
        events_result = service.events().list(calendarId='primary', singleEvents=True).execute()
        google_events_data = events_result.get('items', [])
        logger.info(f"Fetched {len(google_events_data)} total events from Google for user {user.username} after webhook.")

        # --- THIS IS THE NEW, INTELLIGENT SYNC LOGIC ---

        # Step 1: Get the IDs of all events received from Google.
        google_event_ids = {event_data['id'] for event_data in google_events_data}

        # Step 2: Update or Create events based on the Google data.
        for event_data in google_events_data:
            event_id = event_data.get('id')
            if not event_id: continue

            start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
            if not start_raw: continue

            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime') or event_data.get('end', {}).get('date')) if event_data.get('end') else None

            # The update_or_create method is perfect for this.
            # It finds an event with the matching event_id and user, or creates a new one.
            # It then updates all the fields in 'defaults' with the latest info from Google.
            Event.objects.update_or_create(
                user=user, 
                event_id=event_id,
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
        
        # Step 3: Delete any events that are in our database but were NOT in the list from Google.
        # This handles deletions.
        Event.objects.filter(user=user, source='google').exclude(event_id__in=google_event_ids).delete()

        logger.info(f"Sync complete for user {user.username}. Local DB is now up-to-date.")
        # -----------------------------------------------------------

        # Trigger the WebSocket push notification to the browser
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user.id}",
            {"type": "calendar.update", "update": "calendar_changed"}
        )
        logger.info(f"Sent update to WebSocket for user {user.id}")

    except Exception as e:
        logger.error(f"Error syncing events for {user.username} via webhook: {e}", exc_info=True)
        return HttpResponse("Sync failure", status=500)

    return HttpResponse("Webhook processed successfully.", status=200)

@csrf_exempt
def outlook_webhook_receiver(request):
    # 1. Handle Microsoft's initial validation request
    validation_token = request.GET.get('validationToken')
    if validation_token:
        logger.info("Received Outlook validation request. Responding with token.")
        return HttpResponse(validation_token, content_type='text/plain', status=200)

    # 2. Process the actual change notification
    try:
        notification = json.loads(request.body)
        subscription_id = notification['value'][0]['subscriptionId']
        logger.info(f"Received Outlook Webhook notification for subscription: {subscription_id}")

        # 3. Find the user associated with this subscription
        webhook_subscription = OutlookWebhookSubscription.objects.get(subscription_id=subscription_id)
        user = webhook_subscription.user

        # 4. Authenticate with the Microsoft Graph API using the user's saved token
        token = SocialToken.objects.get(account__user=user, account__provider='microsoft')
        # Note: Microsoft Graph token refresh is handled differently and is more complex.
        # For now, we assume a valid token. A full production app would handle token refresh here.
        headers = {'Authorization': f'Bearer {token.token}'}
        graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/events'
        
        # 5. Fetch all events from Outlook to perform a full sync
        response = requests.get(graph_api_endpoint, headers=headers)
        response.raise_for_status()
        outlook_events_data = response.json().get('value', [])
        logger.info(f"Fetched {len(outlook_events_data)} total events from Outlook for user {user.username} after webhook.")
        
        # 6. Perform the intelligent sync (update, create, delete)
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
                user=user, 
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
        
        # Delete local events that were removed from Outlook
        Event.objects.filter(user=user, source='outlook').exclude(event_id__in=outlook_event_ids_in_sync).delete()

        # 7. Trigger the WebSocket push notification
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{user.id}",
            {"type": "calendar.update", "update": "calendar_changed"}
        )
        logger.info(f"Outlook sync complete. Sent update to WebSocket for user {user.id}")

    except Exception as e:
        logger.error(f"Error processing Outlook webhook: {e}", exc_info=True)
    
    # Always return a 200 OK to Microsoft
    return HttpResponse(status=200)
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
