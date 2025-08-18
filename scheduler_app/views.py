# scheduler_app/views.py

from django.core.mail import send_mail,EmailMessage
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
import calendar as cal
import logging,os
import base64
from ics import Calendar, Event as ICSEvent
from datetime import timedelta,time, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from allauth.socialaccount.models import SocialAccount, SocialToken
from .models import Event, GoogleWebhookChannel, OutlookWebhookSubscription, UserProfile
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
from ics import Calendar, Event as ICSEvent, Attendee
from ics.attendee import Attendee


logger = logging.getLogger(__name__)

# --- CORE APPLICATION VIEWS ---

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

# --- CORE APPLICATION VIEWS ---

@login_required
def calendar_view(request, year, month):
    year, month = int(year), int(month)
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    
    all_user_events = Event.objects.filter(user=request.user, date__year=year, date__month=month).select_related('social_account').order_by('start_time')
    
    num_days_in_month = cal.monthrange(year, month)[1]
    events_by_day = {day: [] for day in range(1, num_days_in_month + 1)}
    
    for event in all_user_events:
        day_of_event = event.date.day
        if day_of_event in events_by_day:
            profile_pic_url = event.social_account.get_avatar_url() if event.social_account else None
            events_by_day[day_of_event].append({
                'id': event.id, 'title': event.title, 'source': event.source,
                'start_time': event.start_time.strftime('%I:%M %p') if event.start_time else 'All Day',
                'social_account_id': event.social_account_id, 'profile_pic_url': profile_pic_url
            })

    first_weekday, num_days = cal.monthrange(year, month)
    start_day_of_week = (first_weekday + 1) % 7
    days_data = [{'is_placeholder': True} for _ in range(start_day_of_week)]
    for day in range(1, num_days + 1):
        days_data.append({'day': day, 'events': events_by_day.get(day, []), 'is_placeholder': False})

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
    
    sharing_url = request.build_absolute_uri(reverse('booking_view', kwargs={'sharing_uuid': request.user.profile.sharing_uuid}))
        
    context = {
        'year': year, 'month': month, 'month_name': cal.month_name[month],
        'days_data': days_data, 'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'google_accounts': google_accounts_list, 'microsoft_accounts': microsoft_accounts_list,
        'sharing_url': sharing_url
    }
    return render(request, 'scheduler_app/calendar.html', context)


@login_required
def disconnect_social_account(request, account_id):
    try:
        social_account = get_object_or_404(SocialAccount, id=account_id, user=request.user)
        # If the account being disconnected is the primary booking calendar, clear the setting
        if request.user.profile.primary_booking_calendar == social_account:
            request.user.profile.primary_booking_calendar = None
            request.user.profile.save()
        Event.objects.filter(social_account=social_account).delete()
        social_account.delete()
        messages.success(request, f"Successfully disconnected the account.")
    except Exception as e:
        messages.error(request, f"An error occurred: {e}")
    today = timezone.now()
    return redirect('calendar', year=today.year, month=today.month)


@login_required
def redirect_after_login(request):
    today = timezone.now()
    return redirect('calendar', year=today.year, month=today.month)


@login_required
def add_event(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False); event.user = request.user; event.source = 'local'; event.save()
            return redirect('calendar', year=event.date.year, month=event.date.month)
    else:
        form = EventForm(initial={'date': timezone.now().date()})
    today = timezone.now()
    return render(request, 'scheduler_app/add_event.html', {'form': form, 'year': today.year, 'month': today.month})





def booking_view(request, sharing_uuid):
    """
    Public page for viewing available slots for a user.
    """
    profile = get_object_or_404(UserProfile, sharing_uuid=sharing_uuid)
    owner = profile.user
    
    # For now, we'll hardcode the meeting duration to 30 minutes.
    # We can make this a setting in UserProfile later if needed.
    meeting_duration = 30
    
    # We will show availability for the next 14 days
    today = timezone.now().date()
    availability = {}
    for i in range(14):
        current_date = today + timedelta(days=i)
        
        # Get all existing events for the calendar owner on this day
        busy_times = Event.objects.filter(user=owner, date=current_date, start_time__isnull=False, end_time__isnull=False).values_list('start_time', 'end_time')
        
        # Generate potential slots (e.g., from 9am to 5pm)
        potential_slots = []
        slot_time = timezone.make_aware(datetime.combine(current_date, time(9, 0)))
        end_of_workday = slot_time.replace(hour=17)

        while slot_time < end_of_workday:
            potential_slots.append(slot_time)
            slot_time += timedelta(minutes=meeting_duration)
            
        # Filter out slots that are busy
        available_slots = []
        for slot in potential_slots:
            is_free = True
            slot_end = slot + timedelta(minutes=meeting_duration)
            for busy_start, busy_end in busy_times:
                # Check for any overlap
                if busy_start < slot_end and busy_end > slot:
                    is_free = False
                    break
            if is_free:
                available_slots.append(slot)
        
        if available_slots:
            availability[current_date] = available_slots

    context = {
        'owner': owner,
        'availability': availability,
        'sharing_uuid': sharing_uuid,
    }
    return render(request, 'scheduler_app/booking_page.html', context)



def confirm_booking_view(request, sharing_uuid, datetime_iso):
    """
    Final version using the user's designated primary calendar.
    """
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

            # (The owner notification email logic can be added here)

        except SocialAccount.DoesNotExist:
            return HttpResponse("Booking is unavailable: The calendar owner has not configured a primary calendar for bookings.", status=503)
        except Exception as e:
            return HttpResponse(f"An error occurred while creating the calendar event: {e}", status=500)
            
        return render(request, 'scheduler_app/booking_successful.html', {'owner': owner, 'start_time': start_time})

    context = {'owner': owner, 'start_time': start_time, 'end_time': end_time}
    return render(request, 'scheduler_app/confirm_booking.html', context)




@login_required
def user_settings_view(request):
    """
    This is the final, correct version. It prepares a clean list of accounts
    for the template to use, preventing crashes.
    """
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

    # === THIS IS THE CRITICAL FIX ===
    # We build a clean list of dictionaries here, so the template is simple.
    all_accounts = SocialAccount.objects.filter(user=request.user)
    
    accounts_for_template = []
    for acc in all_accounts:
        # Safely get the email regardless of the provider
        email = acc.extra_data.get('email') or acc.extra_data.get('mail') or acc.extra_data.get('userPrincipalName', '(No email found)')
        accounts_for_template.append({
            'id': acc.id,
            'provider': acc.provider,
            'email': email,
        })
        
    context = {
        # We pass the new, clean list to the template
        'connected_accounts': accounts_for_template,
        'profile': profile
    }
    return render(request, 'scheduler_app/settings.html', context)


@login_required
def event_detail_api(request, event_id):
    event = get_object_or_404(Event, id=event_id, user=request.user)
    account_email = event.social_account.extra_data.get('email') or event.social_account.extra_data.get('mail') if event.social_account else None
    data = {
        'id': event.id, 'title': event.title, 'description': event.description,
        'date': event.date.strftime('%Y-%m-%d'),
        'start_time': event.start_time.strftime('%A, %B %d, %Y at %I:%M %p') if event.start_time else "All-day",
        'end_time': event.end_time.strftime('%A, %B %d, %Y at %I:%M %p') if event.end_time else "",
        'location': event.location, 'meeting_link': event.meeting_link,
        'source': event.source, 'account_email': account_email,
    }
    return JsonResponse(data)



@csrf_exempt
def google_webhook_receiver(request):
    channel_id = request.headers.get('X-Goog-Channel-ID')
    if not channel_id:
        return HttpResponse("Missing Channel ID", status=200)

    try:
        webhook = GoogleWebhookChannel.objects.select_related('social_account__user').get(channel_id=channel_id)
        social_acc = webhook.social_account
        user = social_acc.user
    except GoogleWebhookChannel.DoesNotExist:
        logger.warning(f"Webhook received for unknown Google channel: {channel_id}")
        return HttpResponse("Unknown channel", status=200)

    try:
        token = SocialToken.objects.get(account=social_acc)
        credentials = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token.token = credentials.token
            token.save()
        
        service = build('calendar', 'v3', credentials=credentials)
        events_result = service.events().list(calendarId='primary', singleEvents=True).execute()
        events_data = events_result.get('items', [])
        api_event_ids = {e['id'] for e in events_data if e.get('id')}

        for event_data in events_data:
            event_id = event_data.get('id')
            start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
            if not event_id or not start_raw:
                continue
            
            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime') or event_data.get('end', {}).get('date')) if event_data.get('end') else None
            
            # THIS IS THE CRITICAL FIX:
            # We use get_or_create to check if we already know about this event.
            obj, created = Event.objects.get_or_create(
                social_account=social_acc,
                event_id=event_id,
                defaults={
                    'user': user,
                    'title': event_data.get('summary', 'No Title'),
                    'description': event_data.get('description', ''),
                    'date': start_time.date(),
                    'start_time': start_time,
                    'end_time': end_time,
                    # If we are creating it for the first time, its source is 'google'
                    'source': 'google'
                }
            )
            
            # If the event already existed (wasn't created), we just update its fields
            # but we do NOT change its source. This preserves 'booked_meeting'.
            if not created:
                obj.title = event_data.get('summary', 'No Title')
                obj.description = event_data.get('description', '')
                obj.date = start_time.date()
                obj.start_time = start_time
                obj.end_time = end_time
                obj.save()

        # The delete query is correctly scoped to the specific social_account.
        Event.objects.filter(social_account=social_acc).exclude(event_id__in=api_event_ids).delete()

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(f"user_{user.id}", {"type": "calendar.update", "update": "calendar_changed"})
        logger.info(f"Google webhook sync complete for social account {social_acc.uid}")
        
    except Exception as e:
        logger.error(f"Error processing Google webhook for social_acc {social_acc.uid}: {e}", exc_info=True)
        return HttpResponse("Sync failure", status=500)
    
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
            if not subscription_id:
                continue

            try:
                sub = OutlookWebhookSubscription.objects.select_related('social_account__user').get(subscription_id=subscription_id)
                social_acc = sub.social_account
                user = social_acc.user
                token = SocialToken.objects.get(account=social_acc)
                
                headers = {'Authorization': f'Bearer {token.token}'}
                response = requests.get('https://graph.microsoft.com/v1.0/me/events', headers=headers)
                response.raise_for_status()
                events_data = response.json().get('value', [])
                api_event_ids = {e['id'] for e in events_data if e.get('id')}

                for event_data in events_data:
                    event_id = event_data.get('id')
                    start_raw = event_data.get('start', {}).get('dateTime')
                    if not event_id or not start_raw:
                        continue
                    
                    start_time = parser.parse(start_raw)
                    end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else None
                    
                    # THIS IS THE CRITICAL FIX (same logic as Google):
                    obj, created = Event.objects.get_or_create(
                        social_account=social_acc,
                        event_id=event_id,
                        defaults={
                            'user': user,
                            'title': event_data.get('subject', 'No Title'),
                            'description': event_data.get('bodyPreview', ''),
                            'date': start_time.date(),
                            'start_time': start_time,
                            'end_time': end_time,
                            'source': 'microsoft'
                        }
                    )
                    
                    if not created:
                        obj.title = event_data.get('subject', 'No Title')
                        obj.description = event_data.get('bodyPreview', '')
                        obj.date = start_time.date()
                        obj.start_time = start_time
                        obj.end_time = end_time
                        obj.save()
                
                # The delete query is correctly scoped.
                Event.objects.filter(social_account=social_acc).exclude(event_id__in=api_event_ids).delete()

                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(f"user_{user.id}", {"type": "calendar.update", "update": "calendar_changed"})
                logger.info(f"Outlook webhook sync complete for social account {social_acc.uid}")

            except OutlookWebhookSubscription.DoesNotExist:
                logger.warning(f"Webhook received for unknown Outlook subscription: {subscription_id}")
            except Exception as e:
                logger.error(f"Error processing Outlook webhook for subscription {subscription_id}: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Error decoding Outlook webhook body: {e}", exc_info=True)
    
    return HttpResponse(status=202)