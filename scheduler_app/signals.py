# scheduler_app/signals.py
import uuid
import logging
import requests
from datetime import timedelta, datetime, timezone

from django.conf import settings
from django.dispatch import receiver
from django.urls import reverse
from django.utils.timezone import now

from allauth.socialaccount.models import SocialLogin
from allauth.socialaccount.signals import social_account_added

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from dateutil import parser

from .models import GoogleWebhookChannel, OutlookWebhookSubscription, Event

logger = logging.getLogger(__name__)

@receiver(social_account_added)
def handle_social_account_added(request, sociallogin: SocialLogin, **kwargs):
    """
    This signal is fired ONLY when a new social account is connected.
    Tasks performed:
    1. Initial sync of all events from ALL calendars.
    2. Webhook setup for future updates.
    """
    if not (request and hasattr(request, "user") and request.user.is_authenticated):
        logger.warning("Signal `social_account_added` received without an authenticated user. Aborting.")
        return

    app_user = request.user
    provider = sociallogin.account.provider
    token = sociallogin.token
    social_account = sociallogin.account

    logger.info(f"Signal received for {provider}. Starting sync and webhook setup for user '{app_user.username}'.")

    try:
        total_events_synced = 0
        if provider == 'google':
            credentials = Credentials(
                token=token.token, refresh_token=token.token_secret,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=token.app.client_id, client_secret=token.app.secret
            )
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request()); token.token = credentials.token; token.save()

            service = build('calendar', 'v3', credentials=credentials)
            
            # Get a list of all calendars the user has
            calendar_list = service.calendarList().list().execute()
            
            for calendar_entry in calendar_list.get('items', []):
                calendar_id = calendar_entry['id']
                events_result = service.events().list(calendarId=calendar_id, singleEvents=True).execute()
                events_data = events_result.get('items', [])

                for event_data in events_data:
                    event_id = event_data.get('id')
                    start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
                    if not event_id or not start_raw: continue
                    
                    start_time = parser.parse(start_raw)
                    end_time = parser.parse(event_data.get('end', {}).get('dateTime') or event_data.get('end', {}).get('date')) if event_data.get('end') else start_time

                    Event.objects.update_or_create(
                        social_account=social_account, event_id=event_id,
                        defaults={
                            'user': app_user, 'source': 'google',
                            'title': event_data.get('summary', 'No Title'),
                            'date': start_time.date(),
                            'start_time': start_time, 'end_time': end_time,
                            'calendar_provider_id': calendar_id 
                        }
                    )
                total_events_synced += len(events_data)

        elif provider in ('microsoft', 'MasterCalendarClient'):
            headers = {'Authorization': f'Bearer {token.token}'}

            response = requests.get('https://graph.microsoft.com/v1.0/me/events?$expand=calendar', headers=headers)
            response.raise_for_status()
            events_data = response.json().get('value', [])

            for event_data in events_data:
                event_id = event_data.get('id')
                start_raw = event_data.get('start', {}).get('dateTime')
                if not event_id or not start_raw: continue

                start_time = parser.parse(start_raw)
                end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else start_time

                Event.objects.update_or_create(
                    social_account=social_account, event_id=event_id,
                    defaults={
                        'user': app_user, 'source': 'microsoft',
                        'title': event_data.get('subject', 'No Title'),
                        'date': start_time.date(),
                        'start_time': start_time, 'end_time': end_time,
                        'calendar_provider_id': event_data.get('calendar', {}).get('id') # <-- THE CRITICAL FIX
                    }
                )
            total_events_synced = len(events_data)

        logger.info(f"[SUCCESS] Initial sync for {provider} completed. Synced/updated {total_events_synced} events.")

    except Exception as e:
        logger.error(f"[FAILURE] Initial sync for {provider} failed: {e}", exc_info=True)

    # --- Task 2: Set up the Webhook for Future Updates ---
    try:
        # Use the request to build the absolute URI, safer than NGROK_URL
        webhook_base_url = request.build_absolute_uri('/')

        if provider == 'google':
            GoogleWebhookChannel.objects.filter(social_account=social_account).delete()
            credentials = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
            service = build('calendar', 'v3', credentials=credentials)
            
            # NOTE: Google's watch command on "events" watches ALL calendars by default.
            # We only need to set up one webhook per account.
            webhook_url = webhook_base_url.rstrip('/') + reverse('google_webhook')
            channel_uuid = str(uuid.uuid4())
            watch_request_body = {'id': channel_uuid, 'type': 'web_hook', 'address': webhook_url}

            response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
            expiration = datetime.fromtimestamp(int(response['expiration']) / 1000, tz=timezone.utc) if response.get('expiration') else None

            GoogleWebhookChannel.objects.create(social_account=social_account, channel_id=response['id'], resource_id=response['resourceId'], expiration=expiration)
            logger.info(f"[SUCCESS] Registered Google webhook for {social_account}.")

        elif provider in ('microsoft', 'MasterCalendarClient'):
            OutlookWebhookSubscription.objects.filter(social_account=social_account).delete()
            graph_api_endpoint = 'https://graph.microsoft.com/v1.0/subscriptions'
            headers = {'Authorization': f'Bearer {token.token}', 'Content-Type': 'application/json'}
            expiration_time = now() + timedelta(days=2)
            
            # CRITICAL FIX: The resource should be 'me/events' to get notifications for all calendars
            subscription_payload = {
                "changeType": "created,updated,deleted",
                "notificationUrl": webhook_base_url.rstrip('/') + reverse('outlook_webhook'),
                "resource": "me/events", # This covers events in all calendars
                "expirationDateTime": expiration_time.isoformat(),
                "clientState": "SecretClientState"
            }
            response = requests.post(graph_api_endpoint, headers=headers, json=subscription_payload)
            response.raise_for_status()
            subscription_data = response.json()

            OutlookWebhookSubscription.objects.create(
                social_account=social_account,
                subscription_id=subscription_data['id'],
                expiration_datetime=parser.parse(subscription_data['expirationDateTime'])
            )
            logger.info(f"[SUCCESS] Registered Outlook webhook for {social_account}.")

    except Exception as e:
        logger.error(f"[FAILURE] Webhook setup for {provider} failed: {e}", exc_info=True)