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
    1. Initial sync of all events from that calendar without deleting existing ones.
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

    # --- Task 1: Perform the Initial Sync ---
    try:
        events_data = []

        if provider == 'google':
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
            events_result = service.events().list(calendarId='primary', singleEvents=True).execute()
            events_data = events_result.get('items', [])

            for event_data in events_data:
                event_id = event_data.get('id')
                if not event_id:
                    continue
                start_raw = event_data.get('start', {}).get('dateTime') or event_data.get('start', {}).get('date')
                if not start_raw:
                    continue
                start_time = parser.parse(start_raw)
                end_time = parser.parse(
                    event_data.get('end', {}).get('dateTime') or event_data.get('end', {}).get('date')
                ) if event_data.get('end') else None

                Event.objects.update_or_create(
                    user=app_user,
                    social_account=social_account,
                    event_id=event_id,
                    defaults={
                        'source': 'google',
                        'title': event_data.get('summary', 'No Title'),
                        'date': start_time.date(),
                        'start_time': start_time,
                        'end_time': end_time
                    }
                )

        elif provider in ('microsoft', 'MasterCalendarClient'):
            headers = {'Authorization': f'Bearer {token.token}'}
            response = requests.get('https://graph.microsoft.com/v1.0/me/events', headers=headers)
            response.raise_for_status()
            events_data = response.json().get('value', [])

            for event_data in events_data:
                event_id = event_data.get('id')
                if not event_id:
                    continue
                start_raw = event_data.get('start', {}).get('dateTime')
                if not start_raw:
                    continue
                start_time = parser.parse(start_raw)
                end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else None

                Event.objects.update_or_create(
                    user=app_user,
                    social_account=social_account,
                    event_id=event_id,
                    defaults={
                        'source': 'microsoft',
                        'title': event_data.get('subject', 'No Title'),
                        'date': start_time.date(),
                        'start_time': start_time,
                        'end_time': end_time
                    }
                )

        logger.info(f"[SUCCESS] Initial sync for {provider} completed. Synced/updated {len(events_data)} events.")

    except Exception as e:
        logger.error(f"[FAILURE] Initial sync for {provider} failed: {e}", exc_info=True)

    # --- Task 2: Set up the Webhook for Future Updates ---
    try:
        public_url = settings.NGROK_URL
        if not public_url:
            raise ValueError("NGROK_URL not configured.")

        if provider == 'google':
            GoogleWebhookChannel.objects.filter(social_account=social_account).delete()

            credentials = Credentials(
                token=token.token,
                refresh_token=token.token_secret,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=token.app.client_id,
                client_secret=token.app.secret
            )
            service = build('calendar', 'v3', credentials=credentials)
            webhook_url = public_url + reverse('google_webhook')
            channel_uuid = str(uuid.uuid4())
            watch_request_body = {'id': channel_uuid, 'type': 'web_hook', 'address': webhook_url}

            response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
            expiration = datetime.fromtimestamp(int(response['expiration']) / 1000, tz=timezone.utc) if response.get('expiration') else None

            GoogleWebhookChannel.objects.create(
                social_account=social_account,
                channel_id=response['id'],
                resource_id=response['resourceId'],
                expiration=expiration
            )
            logger.info(f"[SUCCESS] Registered Google webhook for {social_account}.")

        elif provider in ('microsoft', 'MasterCalendarClient'):
            OutlookWebhookSubscription.objects.filter(social_account=social_account).delete()

            graph_api_endpoint = 'https://graph.microsoft.com/v1.0/subscriptions'
            headers = {'Authorization': f'Bearer {token.token}', 'Content-Type': 'application/json'}
            expiration_time = now() + timedelta(days=2)
            subscription_payload = {
                "changeType": "created,updated,deleted",
                "notificationUrl": public_url + reverse('outlook_webhook'),
                "resource": "me/events",
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
