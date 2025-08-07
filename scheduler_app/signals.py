# scheduler_app/signals.py

import uuid
import logging
import requests
from datetime import timedelta

from django.conf import settings
from django.dispatch import receiver
from django.urls import reverse
from django.utils.timezone import now

from allauth.socialaccount.signals import social_account_updated, social_account_added
from allauth.account.signals import user_signed_up

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dateutil import parser

from .models import GoogleWebhookChannel, OutlookWebhookSubscription, UserProfile, Event

logger = logging.getLogger(__name__)

def sync_outlook_events(user, token):
    """Helper function to perform a full sync of Outlook events."""
    try:
        headers = {'Authorization': f'Bearer {token}'}
        graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/events'
        response = requests.get(graph_api_endpoint, headers=headers)
        response.raise_for_status()
        outlook_events_data = response.json().get('value', [])
        logger.info(f"Fetched {len(outlook_events_data)} Outlook events for {user.username}")
        outlook_event_ids = [event_data.get('id') for event_data in outlook_events_data if event_data.get('id')]

        for event_data in outlook_events_data:
            event_id = event_data.get('id')
            if not event_id: continue
            start_raw = event_data.get('start', {}).get('dateTime')
            if not start_raw: continue
            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else None
            Event.objects.update_or_create(
                user=user, event_id=event_id,
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
        Event.objects.filter(user=user, source='outlook').exclude(event_id__in=outlook_event_ids).delete()
        logger.info(f"Outlook events synced successfully for {user.username}")
    except Exception as e:
        logger.error(f"Failed to sync Outlook events for {user.username}: {e}", exc_info=True)

@receiver(social_account_added)
@receiver(social_account_updated)
def setup_webhooks_on_login(sender, request, sociallogin, **kwargs):
    user = sociallogin.user
    provider = sociallogin.account.provider

    if not settings.DEBUG:
        return

    logger.info(f"Signal received for '{provider}' user: {user.username}. Setting up webhook.")

    try:
        public_url = settings.NGROK_URL
        if not public_url:
            raise ValueError("NGROK_URL is not set in your settings.py file.")
    except (AttributeError, ValueError) as e:
        logger.error(f"FATAL: NGROK_URL not configured. Aborting webhook setup. Error: {e}")
        return

    # --- THIS IS THE CORRECTED LOGIC ---
    if provider == 'google':
        try:
            token = sociallogin.token
            credentials = Credentials(
                token=token.token,
                refresh_token=token.token_secret,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=sociallogin.token.app.client_id,
                client_secret=sociallogin.token.app.secret
            )
            service = build('calendar', 'v3', credentials=credentials)
            webhook_url = public_url + reverse('google_webhook')
            channel_uuid = str(uuid.uuid4())
            watch_request_body = {'id': channel_uuid, 'type': 'web_hook', 'address': webhook_url}

            old_channel = GoogleWebhookChannel.objects.filter(user=user).first()
            if old_channel:
                service.channels().stop(body={'id': old_channel.channel_id, 'resourceId': old_channel.resource_id}).execute()
                old_channel.delete()

            response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
            GoogleWebhookChannel.objects.create(
                user=user,
                channel_id=response['id'],
                resource_id=response['resourceId']
            )
            logger.info(f"SUCCESS: Automatically registered Google webhook for {user.username}!")

        except Exception as e:
            logger.error(f"FATAL: Could not register Google webhook: {e}", exc_info=True)

    elif provider == 'MasterCalendarClient':
        try:
            token = sociallogin.token.token
            graph_api_endpoint = 'https://graph.microsoft.com/v1.0/subscriptions'
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            expiration_time = now() + timedelta(days=2)
            subscription_payload = {
               "changeType": "created,updated,deleted",
               "notificationUrl": public_url + reverse('outlook_webhook'),
               "resource": "me/events",
               "expirationDateTime": expiration_time.isoformat(),
               "clientState": "SecretClientState"
            }

            old_subscription = OutlookWebhookSubscription.objects.filter(user=user).first()
            if old_subscription:
                requests.delete(f"{graph_api_endpoint}/{old_subscription.subscription_id}", headers=headers)
                old_subscription.delete()

            # Make the API call
            response = requests.post(graph_api_endpoint, headers=headers, json=subscription_payload)
            
            # --- THIS IS THE NEW DEBUGGING LINE ---
            print(f"\n\n===== MICROSOFT WEBHOOK RESPONSE =====\nSTATUS CODE: {response.status_code}\nBODY: {response.text}\n==================================\n\n")
            # ------------------------------------

            response.raise_for_status()

            subscription_data = response.json()
            OutlookWebhookSubscription.objects.create(
                user=user,
                subscription_id=subscription_data['id'],
                expiration_datetime=parser.parse(subscription_data['expirationDateTime'])
            )
            logger.info(f"SUCCESS: Automatically registered Outlook webhook for {user.username}!")

            # Immediately sync existing Outlook events after login
            sync_outlook_events(user, token)

        except Exception as e:
            logger.error(f"FATAL: Could not register Outlook webhook: {e}", exc_info=True)

@receiver(user_signed_up)
def create_profile_on_social_signup(request, user, **kwargs):
    UserProfile.objects.get_or_create(user=user)