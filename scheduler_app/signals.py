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
from allauth.account.adapter import get_adapter
from datetime import datetime, timezone

from .models import GoogleWebhookChannel, OutlookWebhookSubscription, UserProfile, Event

logger = logging.getLogger(__name__)

def sync_outlook_events(user, token):
    """
    Fetch all Outlook events for the given user and save them to the DB,
    ensuring they are linked to the correct user.
    """
    try:
        headers = {'Authorization': f'Bearer {token}'}
        graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/events'
        response = requests.get(graph_api_endpoint, headers=headers)
        response.raise_for_status()

        outlook_events_data = response.json().get('value', [])
        logger.info(f"Fetched {len(outlook_events_data)} Outlook events for user: {user.username}")

        outlook_event_ids = [event_data.get('id') for event_data in outlook_events_data if event_data.get('id')]

        for event_data in outlook_events_data:
            event_id = event_data.get('id')
            if not event_id: continue
            
            start_raw = event_data.get('start', {}).get('dateTime')
            if not start_raw: continue
            
            start_time = parser.parse(start_raw)
            end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else None

            # The user parameter passed to this function is the correct,
            # logged-in user. We use it here to save the event.
            Event.objects.update_or_create(
                user=user, # <-- This ensures the event is linked to the correct user
                event_id=event_id,
                source='outlook',
                defaults={
                    'title': event_data.get('subject', 'No Title'),
                    'description': event_data.get('bodyPreview', ''),
                    'date': start_time.date(),
                    'start_time': start_time,
                    'end_time': end_time,
                    'etag': event_data.get('@odata.etag', ''),
                    'location': event_data.get('location', {}).get('displayName', ''),
                }
            )

        # Remove old Outlook events for this specific user
        Event.objects.filter(user=user, source='outlook').exclude(event_id__in=outlook_event_ids).delete()
        logger.info(f"Outlook events successfully synced for user: {user.username}")

    except Exception as e:
        logger.error(f"Failed to sync Outlook events for {user.username}: {e}", exc_info=True)
# ---------------------------------------------------


@receiver(social_account_added)
@receiver(social_account_updated)
def setup_webhooks_on_login(sender, request, sociallogin, **kwargs):
    """
    Register provider push notifications mapped to the SocialAccount that was just added or updated.
    We store sociallogin.account.id (an integer) into the webhook rows so incoming webhooks can
    find the exact SocialAccount and therefore the correct app User and token.
    """
    # Prefer the logged-in app user if present (this is important for process=connect flows)
    app_user = request.user if (request and hasattr(request, "user") and request.user.is_authenticated) else sociallogin.user
    provider = sociallogin.account.provider

    # Only run in debug (your original check) — you can remove this guard for prod
    if not settings.DEBUG:
        return

    logger.info(f"Signal received for '{provider}' user: {app_user.username}. Setting up webhook.")

    try:
        public_url = settings.NGROK_URL
        if not public_url:
            raise ValueError("NGROK_URL is not set in settings.py")
    except (AttributeError, ValueError) as e:
        logger.error(f"NGROK_URL not configured. Aborting webhook setup. Error: {e}")
        return

    # The social account id we will persist
    social_account_id = int(sociallogin.account.id)

    if provider == 'google':
        try:
            token = sociallogin.token
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

            # Remove any old channels tied to this social account
            old_channels = GoogleWebhookChannel.objects.filter(social_account_id=social_account_id)
            for c in old_channels:
                try:
                    service.channels().stop(body={'id': c.channel_id, 'resourceId': c.resource_id}).execute()
                except Exception:
                    logger.exception("Error stopping old Google channel (continuing)")
                c.delete()

            response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
            expiration_val = response.get('expiration')
            expiration_dt = None
            if expiration_val:
                try:
                    # If it's a number (milliseconds), convert to datetime
                    if str(expiration_val).isdigit():
                        expiration_dt = datetime.fromtimestamp(int(expiration_val) / 1000, tz=timezone.utc)
                    else:
                        expiration_dt = parser.parse(expiration_val)
                except Exception as e:
                    logger.warning(f"Could not parse expiration value '{expiration_val}': {e}")

            GoogleWebhookChannel.objects.create(
                social_account_id=social_account_id,
                channel_id=response['id'],
                resource_id=response['resourceId'],
                token=token.token,
                expiration=expiration_dt
            )
            logger.info(f"SUCCESS: Registered Google webhook for social_account_id={social_account_id}")

        except Exception as e:
            logger.error(f"Could not register Google webhook: {e}", exc_info=True)

    elif provider in ('microsoft', 'MasterCalendarClient'):
        try:
            # Get token string
            token_str = sociallogin.token.token if hasattr(sociallogin, 'token') else None
            if not token_str:
                logger.warning("No token available for Microsoft sociallogin; skipping subscription creation.")
                return

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

            # Remove old subscriptions for this social account (if any)
            old_subs = OutlookWebhookSubscription.objects.filter(social_account_id=social_account_id)
            for s in old_subs:
                try:
                    requests.delete(f"{graph_api_endpoint}/{s.subscription_id}", headers=headers)
                except Exception:
                    logger.exception("Error deleting old Outlook subscription (continuing)")
                s.delete()

            response = requests.post(graph_api_endpoint, headers=headers, json=subscription_payload)
            print(f"\n\n===== MICROSOFT WEBHOOK RESPONSE =====\nSTATUS CODE: {response.status_code}\nBODY: {response.text}\n==================================\n\n")
            response.raise_for_status()
            subscription_data = response.json()
            OutlookWebhookSubscription.objects.create(
                social_account_id=social_account_id,
                subscription_id=subscription_data['id'],
                expiration_datetime=parser.parse(subscription_data['expirationDateTime'])
            )
            logger.info(f"SUCCESS: Registered Outlook webhook for social_account_id={social_account_id}")

            # Immediately sync events for this social account
            # We pass the app_user (the logged-in app user) so the events are stored under them
            sync_outlook_events(app_user, token_str)

        except Exception as e:
            logger.error(f"Could not register Outlook webhook: {e}", exc_info=True)