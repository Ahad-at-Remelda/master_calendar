# scheduler_app/views.py

from django.shortcuts import render, redirect, get_object_or_404
import calendar as cal
import logging
import base64
from datetime import timedelta,time, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from allauth.socialaccount.models import SocialAccount, SocialToken
from .models import Event, GoogleWebhookChannel, OutlookWebhookSubscription, UserProfile, SyncedCalendar, SyncRelationship, EventMapping
from .forms import EventForm
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
import json
from django.urls import reverse
from dateutil import parser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from datetime import timedelta, date
from .calendar_providers import discover_and_store_calendars 

logger = logging.getLogger(__name__)


# --- HELPER FUNCTIONS FOR BATCH PROCESSING ---
batch_errors = []
successful_mappings_to_create = []

def google_batch_callback(request_id, response, exception):
    """Callback for Google batch requests. Populates a global list with results."""
    global batch_errors, successful_mappings_to_create
    if exception:
        batch_errors.append(f"Request ID {request_id} failed: {exception}")
    else:
        source_event_id, relationship_id = request_id.split(':')
        new_dest_id = response.get('id')
        if new_dest_id:
            successful_mappings_to_create.append(
                EventMapping(
                    relationship_id=int(relationship_id),
                    source_event_id=int(source_event_id),
                    destination_event_id=new_dest_id
                )
            )

# --- CORE APPLICATION VIEWS (UNCHANGED) ---

def get_microsoft_avatar(token: SocialToken):
    try:
        headers = {'Authorization': f'Bearer {token.token}'}
        photo_endpoint = 'https://graph.microsoft.com/v1.0/me/photo/$value'
        response = requests.get(photo_endpoint, headers=headers)
        if response.status_code == 200:
            image_base64 = base64.b64encode(response.content).decode('utf-8')
            return f"data:{response.headers['Content-Type']};base64,{image_base64}"
    except Exception as e:
        logger.error(f"Failed to fetch Microsoft avatar for token {token.id}: {e}")
    return None

def get_base_calendar_context(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    if created:
        logger.info(f"Created missing UserProfile for user: {request.user.username}")

    all_social_accounts = SocialAccount.objects.filter(user=request.user)
    google_accounts_list = [{'id': acc.id, 'email': acc.extra_data.get('email', '(No Email)')} for acc in all_social_accounts.filter(provider='google')]
    
    microsoft_accounts_list = []
    microsoft_accounts = all_social_accounts.filter(provider__in=['microsoft', 'MasterCalendarClient']).prefetch_related('socialtoken_set')
    for acc in microsoft_accounts:
        token = acc.socialtoken_set.first()
        microsoft_accounts_list.append({
            'id': acc.id, 'email': acc.extra_data.get('mail') or acc.extra_data.get('userPrincipalName', '(No Email)'),
            'avatar_url': get_microsoft_avatar(token) if token else None
        })
    
    sharing_url = request.build_absolute_uri(reverse('booking_view', kwargs={'sharing_uuid': user_profile.sharing_uuid}))
    today = timezone.now()
    today_day_url = reverse('calendar_day', kwargs={'year': today.year, 'month': today.month, 'day': today.day})
    today_week_url = reverse('calendar_week', kwargs={'year': today.isocalendar().year, 'week': today.isocalendar().week})
    today_month_url = reverse('calendar_month', kwargs={'year': today.year, 'month': today.month})

    return {
        'google_accounts': google_accounts_list, 'microsoft_accounts': microsoft_accounts_list,
        'sharing_url': sharing_url, 'today_day_url': today_day_url,
        'today_week_url': today_week_url, 'today_month_url': today_month_url,
    }

@login_required
def calendar_view_month(request, year, month):
    context = get_base_calendar_context(request)
    year, month = int(year), int(month)
    current_date = date(year, month, 1)
    prev_month_date = (current_date - timedelta(days=1)).replace(day=1)
    next_month_date = (current_date + timedelta(days=32)).replace(day=1)
    local_tz = timezone.get_current_timezone()
    first_day_of_month = local_tz.localize(datetime(year, month, 1))
    last_day_of_month = (first_day_of_month + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
    all_user_events = Event.objects.filter(user=request.user, start_time__range=(first_day_of_month, last_day_of_month)).select_related('social_account').order_by('start_time')
    num_days_in_month = cal.monthrange(year, month)[1]
    events_by_day = {day: [] for day in range(1, num_days_in_month + 1)}
    for event in all_user_events:
        local_start_time = event.start_time.astimezone(local_tz)
        day_of_event = local_start_time.day
        if day_of_event in events_by_day:
            events_by_day[day_of_event].append(event)
    first_weekday, num_days = cal.monthrange(year, month)
    start_day_of_week = (first_weekday + 1) % 7
    days_data = [{'is_placeholder': True} for _ in range(start_day_of_week)]
    for day in range(1, num_days + 1):
        days_data.append({'day': day, 'events': events_by_day.get(day, []), 'is_placeholder': False})
    context.update({
        "view_mode": "month", "header_title": current_date.strftime("%B %Y"),
        "days_data": days_data,
        "prev_url": reverse('calendar_month', kwargs={'year': prev_month_date.year, 'month': prev_month_date.month}),
        "next_url": reverse('calendar_month', kwargs={'year': next_month_date.year, 'month': next_month_date.month}),
    })
    return render(request, 'scheduler_app/calendar.html', context)

@login_required
def calendar_view_week(request, year, week):
    context = get_base_calendar_context(request)
    year, week = int(year), int(week)
    
    start_of_week_date = date.fromisocalendar(year, week, 1) # Monday
    end_of_week_date = start_of_week_date + timedelta(days=6) # Sunday
    
    # <-- MAJOR FIX: Query by timezone-aware range instead of just date -->
    local_tz = timezone.get_current_timezone()
    start_of_week = local_tz.localize(datetime.combine(start_of_week_date, time.min))
    end_of_week = local_tz.localize(datetime.combine(end_of_week_date, time.max))
    
    prev_week_date = start_of_week_date - timedelta(days=7)
    next_week_date = start_of_week_date + timedelta(days=7)
    
    all_user_events = Event.objects.filter(
        user=request.user, 
        start_time__range=[start_of_week, end_of_week]
    ).select_related('social_account').order_by('start_time')

    week_days_dates = [start_of_week_date + timedelta(days=i) for i in range(7)]
    events_by_day = {d: [] for d in week_days_dates}

    for event in all_user_events:
        local_start_time = event.start_time.astimezone(local_tz)
        event_date = local_start_time.date()
        if event_date in events_by_day:
            events_by_day[event_date].append(event)
        
    context.update({
        "view_mode": "week",
        "header_title": f"{start_of_week_date.strftime('%b %d')} - {end_of_week_date.strftime('%b %d, %Y')}",
        "week_days": [{'date': d, 'events': events_by_day.get(d, [])} for d in week_days_dates],
        "prev_url": reverse('calendar_week', kwargs={'year': prev_week_date.isocalendar().year, 'week': prev_week_date.isocalendar().week}),
        "next_url": reverse('calendar_week', kwargs={'year': next_week_date.isocalendar().year, 'week': next_week_date.isocalendar().week}),
    })
    return render(request, 'scheduler_app/calendar.html', context)

@login_required
def calendar_view_day(request, year, month, day):
    context = get_base_calendar_context(request)
    
    current_date = date(int(year), int(month), int(day))
    prev_date = current_date - timedelta(days=1)
    next_date = current_date + timedelta(days=1)
    
    # <-- MAJOR FIX: Query by timezone-aware range instead of just date -->
    local_tz = timezone.get_current_timezone()
    start_of_day = local_tz.localize(datetime.combine(current_date, time.min))
    end_of_day = local_tz.localize(datetime.combine(current_date, time.max))

    all_user_events = Event.objects.filter(
        user=request.user, 
        start_time__range=(start_of_day, end_of_day)
    ).select_related('social_account').order_by('start_time')
    
    context.update({
        "view_mode": "day",
        "events": all_user_events,
        "header_title": current_date.strftime("%A, %B %d, %Y"),
        "prev_url": reverse('calendar_day', kwargs={'year': prev_date.year, 'month': prev_date.month, 'day': prev_date.day}),
        "next_url": reverse('calendar_day', kwargs={'year': next_date.year, 'month': next_date.month, 'day': next_date.day}),
    })
    return render(request, 'scheduler_app/calendar.html', context)


@login_required
def disconnect_social_account(request, account_id):
    try:
        social_account = get_object_or_404(SocialAccount, id=account_id, user=request.user)
        if request.user.profile.primary_booking_calendar == social_account:
            request.user.profile.primary_booking_calendar = None
            request.user.profile.save()
        Event.objects.filter(social_account=social_account).delete()
        social_account.delete()
        messages.success(request, f"Successfully disconnected the account.")
    except Exception as e:
        messages.error(request, f"An error occurred: {e}")
    today = timezone.now()
    return redirect('calendar_month', year=today.year, month=today.month)


@login_required
def redirect_after_login(request):
    today = timezone.now()
    return redirect('calendar_month', year=today.year, month=today.month)


@login_required
def add_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False); event.user = request.user; event.source = 'local'; event.save()
            return redirect('calendar_month', year=event.date.year, month=event.date.month)
    else:
        form = EventForm(initial={'date': timezone.now().date()})
    today = timezone.now()
    return render(request, 'scheduler_app/add_event.html', {'form': form, 'year': today.year, 'month': today.month})


def booking_view(request, sharing_uuid):
    profile = get_object_or_404(UserProfile, sharing_uuid=sharing_uuid)
    owner = profile.user
    meeting_duration = 30
    today = timezone.now().date()
    availability = {}
    for i in range(14):
        current_date = today + timedelta(days=i)
        busy_times = Event.objects.filter(user=owner, date=current_date, start_time__isnull=False, end_time__isnull=False).values_list('start_time', 'end_time')
        potential_slots = []
        slot_time = timezone.make_aware(datetime.combine(current_date, time(9, 0)))
        end_of_workday = slot_time.replace(hour=17)

        while slot_time < end_of_workday:
            potential_slots.append(slot_time)
            slot_time += timedelta(minutes=meeting_duration)
            
        available_slots = []
        for slot in potential_slots:
            is_free = True
            slot_end = slot + timedelta(minutes=meeting_duration)
            for busy_start, busy_end in busy_times:
                if busy_start < slot_end and busy_end > slot:
                    is_free = False
                    break
            if is_free:
                available_slots.append(slot)
        
        if available_slots:
            availability[current_date] = available_slots

    context = {
        'owner': owner, 'availability': availability, 'sharing_uuid': sharing_uuid,
    }
    return render(request, 'scheduler_app/booking_page.html', context)


def confirm_booking_view(request, sharing_uuid, datetime_iso):
    profile = get_object_or_404(UserProfile, sharing_uuid=sharing_uuid)
    owner = profile.user
    meeting_duration = 30
    start_time = parser.parse(datetime_iso)
    end_time = start_time + timedelta(minutes=meeting_duration)

    if request.method == 'POST':
        booker_name = request.POST.get('name', 'Guest')
        booker_email = request.POST.get('email')
        meeting_title = request.POST.get('title', f"Meeting with {booker_name}")
        guest_list_str = request.POST.get('guests', '')
        guest_emails = [email.strip() for email in guest_list_str.split(',') if email.strip()]

        try:
            primary_calendar = owner.profile.primary_booking_calendar
            if not primary_calendar:
                raise SocialAccount.DoesNotExist("Owner has not selected a primary booking calendar.")

            token = SocialToken.objects.get(account=primary_calendar)
            credentials = Credentials(
                token=token.token, refresh_token=token.token_secret,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=token.app.client_id, client_secret=token.app.secret
            )
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request()); token.token = credentials.token; token.save()

            service = build('calendar', 'v3', credentials=credentials)
            
            attendees = [
                {'email': owner.email, 'organizer': True, 'responseStatus': 'accepted'},
                {'email': booker_email, 'responseStatus': 'accepted'},
            ]
            for guest_email in guest_emails:
                attendees.append({'email': guest_email, 'responseStatus': 'needsAction'})
            
            event_body = {
                'summary': meeting_title,
                'description': f"Booked via Master Calendar by: {booker_name} ({booker_email})",
                'start': {'dateTime': start_time.isoformat(), 'timeZone': 'UTC'},
                'end': {'dateTime': end_time.isoformat(), 'timeZone': 'UTC'},
                'attendees': attendees,
                'reminders': {'useDefault': True},
            }

            created_event = service.events().insert(calendarId='primary', body=event_body, sendUpdates='all').execute()
            
            Event.objects.create(
                user=owner, source='booked_meeting', social_account=primary_calendar,
                event_id=created_event.get('id'), title=meeting_title,
                date=start_time.date(), start_time=start_time, end_time=end_time
            )

        except SocialAccount.DoesNotExist:
            return HttpResponse("Booking is unavailable: The calendar owner has not configured a primary calendar for bookings.", status=503)
        except Exception as e:
            return HttpResponse(f"An error occurred while creating the calendar event: {e}", status=500)
            
        return render(request, 'scheduler_app/booking_successful.html', {'owner': owner, 'start_time': start_time})

    context = {'owner': owner, 'start_time': start_time, 'end_time': end_time}
    return render(request, 'scheduler_app/confirm_booking.html', context)


@login_required
def user_settings_view(request):
    profile = request.user.profile
    if request.method == 'POST':
        primary_calendar_id = request.POST.get('primary_booking_calendar')
        if primary_calendar_id:
            try:
                social_account = SocialAccount.objects.get(id=primary_calendar_id, user=request.user)
                profile.primary_booking_calendar = social_account
                profile.save()
                messages.success(request, "Your primary booking calendar has been updated.")
            except SocialAccount.DoesNotExist:
                messages.error(request, "Invalid account selected.")
        else:
            profile.primary_booking_calendar = None
            profile.save()
            messages.info(request, "Primary booking calendar has been cleared.")
        return redirect('user_settings')

    all_accounts = SocialAccount.objects.filter(user=request.user)
    
    accounts_for_template = []
    for acc in all_accounts:
        email = acc.extra_data.get('email') or acc.extra_data.get('mail') or acc.extra_data.get('userPrincipalName', '(No email found)')
        accounts_for_template.append({
            'id': acc.id, 'provider': acc.provider, 'email': email,
        })
        
    context = {
        'connected_accounts': accounts_for_template, 'profile': profile
    }
    return render(request, 'scheduler_app/settings.html', context)


@login_required
def event_detail_api(request, event_id):
    event = get_object_or_404(Event, id=event_id, user=request.user)
    account_email = event.social_account.extra_data.get('email') or event.social_account.extra_data.get('mail') if event.social_account else None
    
    data = {
        'id': event.id, 'title': event.title, 'description': event.description,
        'date': event.date.strftime('%Y-%m-%d'),
        'start_time': event.start_time.isoformat() if event.start_time else None,
        'end_time': event.end_time.isoformat() if event.end_time else None,
        'location': event.location, 'meeting_link': event.meeting_link,
        'source': event.source, 'account_email': account_email,
    }
    return JsonResponse(data)


# =======================================================================
# == THE SYNC ENGINE ====================================================
# =======================================================================
def trigger_sync_for_event(source_event: Event):
    relevant_syncs = SyncRelationship.objects.filter(
        source_calendar__social_account=source_event.social_account,
        source_calendar__calendar_id=source_event.calendar_provider_id,
        is_active=True
    ).select_related('destination_calendar__social_account')

    for sync in relevant_syncs:
        dest_calendar = sync.destination_calendar
        sync_type = sync.sync_type
        event_body = {
            'summary': source_event.title if sync_type == 'full_details' else 'Busy',
            'description': source_event.description if sync_type == 'full_details' else 'This time is booked.',
            'location': source_event.location if sync_type == 'full_details' else '',
            'start': {'dateTime': source_event.start_time.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': source_event.end_time.isoformat(), 'timeZone': 'UTC'},
        }
        mapping = EventMapping.objects.filter(relationship=sync, source_event=source_event).first()
        try:
            if dest_calendar.provider == 'google':
                token = SocialToken.objects.get(account=dest_calendar.social_account)
                creds = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request()); token.token = creds.token; token.save()
                service = build('calendar', 'v3', credentials=creds)
                if mapping:
                    service.events().update(calendarId=dest_calendar.calendar_id, eventId=mapping.destination_event_id, body=event_body).execute()
                    logger.info(f"Updated event {mapping.destination_event_id} in Google Calendar '{dest_calendar.name}'")
                else:
                    created_event = service.events().insert(calendarId=dest_calendar.calendar_id, body=event_body).execute()
                    EventMapping.objects.create(relationship=sync, source_event=source_event, destination_event_id=created_event['id'])
                    logger.info(f"Created new event {created_event['id']} in Google Calendar '{dest_calendar.name}'")
            elif dest_calendar.provider == 'microsoft':
                token = SocialToken.objects.get(account=dest_calendar.social_account)
                headers = {'Authorization': f'Bearer {token.token}', 'Content-Type': 'application/json'}
                ms_event_body = {'subject': event_body['summary'], 'body': {'contentType': 'HTML', 'content': event_body['description']},'location': {'displayName': event_body['location']},'start': {'dateTime': event_body['start']['dateTime'], 'timeZone': 'UTC'},'end': {'dateTime': event_body['end']['dateTime'], 'timeZone': 'UTC'}}
                if mapping:
                    url = f"https://graph.microsoft.com/v1.0/me/events/{mapping.destination_event_id}"
                    requests.patch(url, headers=headers, json=ms_event_body).raise_for_status()
                    logger.info(f"Updated event {mapping.destination_event_id} in Outlook Calendar '{dest_calendar.name}'")
                else:
                    url = f"https://graph.microsoft.com/v1.0/me/calendars/{dest_calendar.calendar_id}/events"
                    response = requests.post(url, headers=headers, json=ms_event_body)
                    response.raise_for_status()
                    created_event = response.json()
                    EventMapping.objects.create(relationship=sync, source_event=source_event, destination_event_id=created_event['id'])
                    logger.info(f"Created new event {created_event['id']} in Outlook Calendar '{dest_calendar.name}'")
        except Exception as e:
            logger.error(f"Failed to sync event {source_event.id} for sync {sync.id}: {e}")

def delete_synced_event(source_event: Event):
    mappings = EventMapping.objects.filter(source_event=source_event)
    for mapping in mappings:
        dest_calendar = mapping.relationship.destination_calendar
        try:
            if dest_calendar.provider == 'google':
                token = SocialToken.objects.get(account=dest_calendar.social_account)
                creds = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request()); token.token = creds.token; token.save()
                service = build('calendar', 'v3', credentials=creds)
                service.events().delete(calendarId=dest_calendar.calendar_id, eventId=mapping.destination_event_id).execute()
                logger.info(f"Deleted synced event {mapping.destination_event_id} from Google Calendar '{dest_calendar.name}'")
            elif dest_calendar.provider == 'microsoft':
                token = SocialToken.objects.get(account=dest_calendar.social_account)
                headers = {'Authorization': f'Bearer {token.token}'}
                url = f"https://graph.microsoft.com/v1.0/me/events/{mapping.destination_event_id}"
                requests.delete(url, headers=headers) # raise_for_status() not needed for delete
                logger.info(f"Deleted synced event {mapping.destination_event_id} from Outlook Calendar '{dest_calendar.name}'")
            mapping.delete()
        except Exception as e:
            # We log the error but continue, in case the event was already deleted manually
            logger.error(f"Failed to delete synced event for mapping {mapping.id}: {e}")


# --- UPGRADED WEBHOOKS ---
@csrf_exempt
def google_webhook_receiver(request):
    channel_id = request.headers.get('X-Goog-Channel-ID')
    try:
        webhook = GoogleWebhookChannel.objects.select_related('social_account__user').get(channel_id=channel_id)
        social_acc = webhook.social_account
        user = social_acc.user
        token = SocialToken.objects.get(account=social_acc)
        creds = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request()); token.token = creds.token; token.save()
        service = build('calendar', 'v3', credentials=creds)
        
        calendar_list = service.calendarList().list().execute()
        all_events_data = []
        for calendar_entry in calendar_list.get('items', []):
            try:
                events_result = service.events().list(calendarId=calendar_entry['id'], singleEvents=True).execute()
                for event in events_result.get('items', []):
                    event['calendar_provider_id'] = calendar_entry['id']
                    all_events_data.append(event)
            except Exception as e:
                logger.error(f"Could not fetch events from calendar {calendar_entry['id']} for user {user.username}: {e}")
        
        api_event_ids = {e['id'] for e in all_events_data}

        for event_data in all_events_data:
            event_id = event_data.get('id')
            start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
            if not event_id or not start_raw: continue
            
            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime') or event_data.get('end', {}).get('date')) if event_data.get('end') else start_time
            
            defaults = {'user': user, 'title': event_data.get('summary', 'No Title'),'description': event_data.get('description', ''),'date': start_time.date(),'start_time': start_time,'end_time': end_time,'source': 'google','calendar_provider_id': event_data.get('calendar_provider_id')}
            saved_event, created = Event.objects.update_or_create(social_account=social_acc, event_id=event_id, defaults=defaults)
            trigger_sync_for_event(saved_event)
            
        db_events = Event.objects.filter(social_account=social_acc)
        deleted_provider_ids = {e.event_id for e in db_events} - api_event_ids
        for provider_id in deleted_provider_ids:
            try:
                event_to_delete = Event.objects.get(event_id=provider_id, social_account=social_acc)
                delete_synced_event(event_to_delete)
                event_to_delete.delete()
                logger.info(f"Deleted event {provider_id} from local DB and synced destinations.")
            except Event.DoesNotExist:
                continue

        async_to_sync(get_channel_layer().group_send)(f"user_{user.id}", {"type": "calendar.update", "update": "calendar_changed"})
        logger.info(f"Google webhook sync complete for social account {social_acc.uid}")
    except Exception as e:
        logger.error(f"Error processing Google webhook: {e}", exc_info=True)
    return HttpResponse("OK", status=200)

@csrf_exempt
def outlook_webhook_receiver(request):
    validation_token = request.GET.get('validationToken')
    if validation_token:
        return HttpResponse(validation_token, content_type='text/plain')

    try:
        notification = json.loads(request.body)
        for notif in notification.get('value', []):
            subscription_id = notif.get('subscriptionId')
            try:
                sub = OutlookWebhookSubscription.objects.select_related('social_account__user').get(subscription_id=subscription_id)
                social_acc = sub.social_account
                user = social_acc.user
                token = SocialToken.objects.get(account=social_acc)
                headers = {'Authorization': f'Bearer {token.token}'}
                events_endpoint = "https://graph.microsoft.com/v1.0/me/events?$expand=calendar"
                response = requests.get(events_endpoint, headers=headers)
                response.raise_for_status()
                events_data = response.json().get('value', [])
                api_event_ids = {e['id'] for e in events_data}

                for event_data in events_data:
                    event_id = event_data.get('id')
                    start_raw = event_data.get('start', {}).get('dateTime')
                    if not event_id or not start_raw: continue

                    start_time = parser.parse(start_raw)
                    end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else start_time
                    
                    defaults = {'user': user,'title': event_data.get('subject', 'No Title'),'description': event_data.get('bodyPreview', ''),'date': start_time.date(),'start_time': start_time,'end_time': end_time,'source': 'microsoft','calendar_provider_id': event_data.get('calendar', {}).get('id')}
                    saved_event, created = Event.objects.update_or_create(social_account=social_acc, event_id=event_id, defaults=defaults)
                    trigger_sync_for_event(saved_event)
                
                db_events = Event.objects.filter(social_account=social_acc)
                deleted_provider_ids = {e.event_id for e in db_events} - api_event_ids
                for provider_id in deleted_provider_ids:
                    try:
                        event_to_delete = Event.objects.get(event_id=provider_id, social_account=social_acc)
                        delete_synced_event(event_to_delete)
                        event_to_delete.delete()
                        logger.info(f"Deleted event {provider_id} from local DB and synced destinations.")
                    except Event.DoesNotExist:
                        continue
                
                async_to_sync(get_channel_layer().group_send)(f"user_{user.id}", {"type": "calendar.update", "update": "calendar_changed"})
                logger.info(f"Outlook webhook sync complete for social account {social_acc.uid}")
            except Exception as e:
                logger.error(f"Error processing Outlook subscription {subscription_id}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error decoding Outlook webhook body: {e}", exc_info=True)
    return HttpResponse(status=202)


# =======================================================================
# == FULLY IMPLEMENTED SYNC CREATION & DELETION VIEWS ===================
# =======================================================================
@login_required
def sync_calendars_view(request):
    discover_and_store_calendars(request.user)
    all_user_calendars = SyncedCalendar.objects.filter(user=request.user).select_related('social_account')
    active_syncs = SyncRelationship.objects.filter(user=request.user, is_active=True).select_related('source_calendar__social_account', 'destination_calendar__social_account')
    
    calendars_for_template = []
    for cal in all_user_calendars:
        email = cal.social_account.extra_data.get('email') or cal.social_account.extra_data.get('mail') or '(No Email Found)'
        calendars_for_template.append({'id': cal.id, 'provider': cal.provider, 'name': cal.name, 'display_email': email})

    active_syncs_for_template = []
    for sync in active_syncs:
        source_email = sync.source_calendar.social_account.extra_data.get('email') or sync.source_calendar.social_account.extra_data.get('mail')
        dest_email = sync.destination_calendar.social_account.extra_data.get('email') or sync.destination_calendar.social_account.extra_data.get('mail')
        active_syncs_for_template.append({'id': sync.id, 'source_provider': sync.source_calendar.provider, 'source_name': sync.source_calendar.name, 'source_email': source_email, 'dest_provider': sync.destination_calendar.provider, 'dest_name': sync.destination_calendar.name, 'dest_email': dest_email, 'sync_type_display': sync.get_sync_type_display()})

    context = get_base_calendar_context(request)
    context.update({'all_calendars': calendars_for_template, 'active_syncs': active_syncs_for_template})
    return render(request, 'scheduler_app/sync_calendars.html', context)

@login_required
def create_sync_relationship(request):
    if request.method != 'POST':
        return redirect('sync_calendars')
    user = request.user
    source_cal_id = request.POST.get('source_calendar_id')
    dest_cal_id = request.POST.get('destination_calendar_id')
    sync_type = request.POST.get('sync_type')

    if not all([source_cal_id, dest_cal_id, sync_type]) or source_cal_id == dest_cal_id:
        messages.error(request, "Invalid form submission.")
        return redirect('sync_calendars')

    try:
        source_calendar = SyncedCalendar.objects.get(id=source_cal_id, user=user)
        destination_calendar = SyncedCalendar.objects.get(id=dest_cal_id, user=user)
    except SyncedCalendar.DoesNotExist:
        messages.error(request, "One of the selected calendars could not be found.")
        return redirect('sync_calendars')

    relationship, created = SyncRelationship.objects.get_or_create(user=user, source_calendar=source_calendar, destination_calendar=destination_calendar, defaults={'sync_type': sync_type})
    if not created:
        messages.info(request, "A sync relationship between these calendars already exists.")
        return redirect('sync_calendars')

    events_to_sync = Event.objects.filter(social_account=source_calendar.social_account, calendar_provider_id=source_calendar.calendar_id)
    if not events_to_sync:
        messages.success(request, f"Sync relationship created. No initial events to sync.")
        return redirect('sync_calendars')

    try:
        global batch_errors, successful_mappings_to_create
        batch_errors.clear()
        successful_mappings_to_create.clear()

        if destination_calendar.provider == 'google':
            token = SocialToken.objects.get(account=destination_calendar.social_account)
            creds = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request()); token.token = creds.token; token.save()
            service = build('calendar', 'v3', credentials=creds)
            batch = service.new_batch_http_request(callback=google_batch_callback)
            for i, event in enumerate(events_to_sync):
                event_body = {'summary': event.title if sync_type == 'full_details' else 'Busy','description': event.description if sync_type == 'full_details' else 'This time is booked.','location': event.location if sync_type == 'full_details' else '','start': {'dateTime': event.start_time.isoformat(), 'timeZone': 'UTC'},'end': {'dateTime': event.end_time.isoformat(), 'timeZone': 'UTC'}}
                batch.add(service.events().insert(calendarId=destination_calendar.calendar_id, body=event_body), request_id=f"{event.id}:{relationship.id}")
            batch.execute()

        elif destination_calendar.provider == 'microsoft':
            token = SocialToken.objects.get(account=destination_calendar.social_account)
            headers = {'Authorization': f'Bearer {token.token}', 'Content-Type': 'application/json'}
            batch_requests = []
            for event in events_to_sync:
                ms_event_body = {'subject': event.title if sync_type == 'full_details' else 'Busy','body': {'contentType': 'HTML', 'content': event.description if sync_type == 'full_details' else ''},'location': {'displayName': event.location if sync_type == 'full_details' else ''},'start': {'dateTime': event.start_time.isoformat(), 'timeZone': 'UTC'},'end': {'dateTime': event.end_time.isoformat(), 'timeZone': 'UTC'}}
                batch_requests.append({"id": str(event.id),"method": "POST","url": f"/me/calendars/{destination_calendar.calendar_id}/events","body": ms_event_body,"headers": {"Content-Type": "application/json"}})
            
            for i in range(0, len(batch_requests), 20):
                chunk = batch_requests[i:i+20]
                response = requests.post("https://graph.microsoft.com/v1.0/$batch", headers=headers, json={"requests": chunk})
                response.raise_for_status()
                for resp in response.json().get('responses', []):
                    if resp.get('status') in [200, 201]:
                        successful_mappings_to_create.append(EventMapping(relationship=relationship, source_event_id=int(resp['id']), destination_event_id=resp['body']['id']))

        if batch_errors:
             raise Exception("Batch processing failed for some requests.")

        EventMapping.objects.bulk_create(successful_mappings_to_create)
        messages.success(request, f"Successfully copied {len(successful_mappings_to_create)} events to '{destination_calendar.name}'.")

    except Exception as e:
        messages.error(request, f"Failed to sync events: {e}")
        relationship.delete()
        
    return redirect('sync_calendars')

@login_required
def delete_sync_relationship(request, sync_id):
    if request.method != 'POST':
        return redirect('sync_calendars')
    try:
        relationship = SyncRelationship.objects.get(id=sync_id, user=request.user)
    except SyncRelationship.DoesNotExist:
        messages.error(request, "Sync relationship not found.")
        return redirect('sync_calendars')

    event_mappings = EventMapping.objects.filter(relationship=relationship)
    destination_calendar = relationship.destination_calendar

    if not event_mappings:
        relationship.delete()
        messages.success(request, "Sync relationship removed.")
        return redirect('sync_calendars')

    try:
        if destination_calendar.provider == 'google':
            token = SocialToken.objects.get(account=destination_calendar.social_account)
            creds = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request()); token.token = creds.token; token.save()
            service = build('calendar', 'v3', credentials=creds)
            batch = service.new_batch_http_request()
            for mapping in event_mappings:
                batch.add(service.events().delete(calendarId=destination_calendar.calendar_id, eventId=mapping.destination_event_id))
            batch.execute()

        elif destination_calendar.provider == 'microsoft':
            token = SocialToken.objects.get(account=destination_calendar.social_account)
            headers = {'Authorization': f'Bearer {token.token}', 'Content-Type': 'application/json'}
            batch_requests = []
            for mapping in event_mappings:
                batch_requests.append({"id": str(mapping.id),"method": "DELETE","url": f"/me/events/{mapping.destination_event_id}"})
            for i in range(0, len(batch_requests), 20):
                chunk = batch_requests[i:i+20]
                requests.post("https://graph.microsoft.com/v1.0/$batch", headers=headers, json={"requests": chunk}).raise_for_status()

        relationship.delete() # Cascade delete will handle the mappings
        messages.success(request, f"Successfully removed sync and deleted {event_mappings.count()} events from '{destination_calendar.name}'.")
    except Exception as e:
        messages.error(request, f"An error occurred while deleting events: {e}")
            
    return redirect('sync_calendars')