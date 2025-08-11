# scheduler_app/signals.py

import uuid
import logging
import requests
from datetime import timedelta

from django.conf import settings
from django.dispatch import receiver
from django.urls import reverse
from django.utils.timezone import now

# Correct, specific imports for allauth signals and models
from allauth.socialaccount.models import SocialToken, SocialLogin
from allauth.socialaccount.signals import social_account_added

# Correct, specific imports for Google API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from dateutil import parser
from datetime import datetime, timezone

from .models import GoogleWebhookChannel, OutlookWebhookSubscription, Event

logger = logging.getLogger(__name__)


def sync_google_events(user, token: SocialToken):
    """
    Fetches all Google events for the given user's token and saves them to the DB.
    This is called ONLY when a new account is connected.
    """
    try:
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
            token.token_secret = credentials.refresh_token or token.token_secret
            token.save()

        service = build('calendar', 'v3', credentials=credentials)
        events_result = service.events().list(calendarId='primary', singleEvents=True).execute()
        google_events_data = events_result.get('items', [])
        logger.info(f"[Initial Sync] Fetched {len(google_events_data)} Google events for Django user: {user.username}")

        google_event_ids_from_api = {event_data['id'] for event_data in google_events_data if 'id' in event_data}

        for event_data in google_events_data:
            event_id = event_data.get('id')
            if not event_id: continue
            
            start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
            if not start_raw: continue

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
                    'is_recurring': 'recurringEventId' in event_data,
                }
            )

        Event.objects.filter(user=user, source='google', event_id__isnull=False).exclude(event_id__in=google_event_ids_from_api).delete()
        logger.info(f"[Initial Sync] Google events successfully synced for Django user: {user.username}")

    except Exception as e:
        logger.error(f"[Initial Sync] Failed to sync Google events for {user.username}: {e}", exc_info=True)


def sync_outlook_events(user, token_str: str):
    """
    Fetches all Outlook events for the given user and saves them to the DB.
    This is called ONLY when a new account is connected.
    """
    try:
        headers = {'Authorization': f'Bearer {token_str}'}
        graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/events'
        response = requests.get(graph_api_endpoint, headers=headers)
        response.raise_for_status()

        outlook_events_data = response.json().get('value', [])
        logger.info(f"[Initial Sync] Fetched {len(outlook_events_data)} Outlook events for Django user: {user.username}")

        outlook_event_ids_from_api = {event_data.get('id') for event_data in outlook_events_data if event_data.get('id')}

        for event_data in outlook_events_data:
            event_id = event_data.get('id')
            if not event_id: continue

            start_raw = event_data.get('start', {}).get('dateTime')
            if not start_raw: continue
            
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

        Event.objects.filter(user=user, source='microsoft', event_id__isnull=False).exclude(event_id__in=outlook_event_ids_from_api).delete()
        logger.info(f"[Initial Sync] Outlook events successfully synced for Django user: {user.username}")

    except Exception as e:
        logger.error(f"[Initial Sync] Failed to sync Outlook events for {user.username}: {e}", exc_info=True)


@receiver(social_account_added)
def handle_social_account_added(request, sociallogin: SocialLogin, **kwargs):
    """
    This signal handler fires ONLY when a new social account is CONNECTED to a user.
    It does NOT fire on a simple login. This is the correct place to trigger
    the initial sync and webhook setup.
    """
    if not (request and hasattr(request, "user") and request.user.is_authenticated):
        logger.warning("Social account added signal received without an authenticated user in the request. Aborting.")
        return
        
    app_user = request.user
    provider = sociallogin.account.provider
    logger.info(f"Signal `social_account_added` received for provider '{provider}'. Syncing events for Django user '{app_user.username}'.")

    try:
        public_url = settings.NGROK_URL
        if not public_url:
            raise ValueError("NGROK_URL is not set in settings.py")
            
        social_account_id = int(sociallogin.account.id)

        if provider == 'google':
            token = sociallogin.token
            credentials = Credentials(token=token.token, refresh_token=token.token_secret, token_uri='https://oauth2.googleapis.com/token', client_id=token.app.client_id, client_secret=token.app.secret)
            service = build('calendar', 'v3', credentials=credentials)
            webhook_url = public_url + reverse('google_webhook')
            channel_uuid = str(uuid.uuid4())
            watch_request_body = {'id': channel_uuid, 'type': 'web_hook', 'address': webhook_url}
            
            GoogleWebhookChannel.objects.filter(social_account_id=social_account_id).delete()
            
            response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
            
            expiration_val = response.get('expiration')
            expiration_dt = None
            if expiration_val and str(expiration_val).isdigit():
                expiration_dt = datetime.fromtimestamp(int(expiration_val) / 1000, tz=timezone.utc)

            GoogleWebhookChannel.objects.create(
                social_account_id=social_account_id,
                channel_id=response['id'],
                resource_id=response['resourceId'],
                token=token.token,
                expiration=expiration_dt
            )
            logger.info(f"SUCCESS: Registered Google webhook for social_account_id={social_account_id}")

            sync_google_events(app_user, token)

        elif provider in ('microsoft', 'MasterCalendarClient'):
            token_str = sociallogin.token.token
            graph_api_endpoint = 'https://graph.microsoft.com/v1.0/subscriptions'
            headers = {'Authorization': f'Bearer {token_str}', 'Content-Type': 'application/json'}
            expiration_time = now() + timedelta(days=2)
            subscription_payload = {
               "changeType": "created,updated,deleted",
               "notificationUrl": public_url + reverse('outlook_webhook'),
               "resource": "me/events",
               "expirationDateTime": expiration_time.isoformat(),
               "clientState": "SecretClientState"
            }
            
            OutlookWebhookSubscription.objects.filter(social_account_id=social_account_id).delete()
            
            response = requests.post(graph_api_endpoint, headers=headers, json=subscription_payload)
            response.raise_for_status()
            subscription_data = response.json()
            
            OutlookWebhookSubscription.objects.create(
                social_account_id=social_account_id,
                subscription_id=subscription_data['id'],
                expiration_datetime=parser.parse(subscription_data['expirationDateTime'])
            )
            logger.info(f"SUCCESS: Registered Outlook webhook for social_account_id={social_account_id}")
            
            sync_outlook_events(app_user, token_str)

    except Exception as e:
        logger.error(f"Error during webhook setup or initial sync for user {app_user.username}: {e}", exc_info=True)