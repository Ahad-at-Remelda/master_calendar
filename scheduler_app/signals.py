# scheduler_app/signals.py

import uuid
import logging
import requests
from datetime import timedelta

from django.conf import settings
from django.dispatch import receiver
from django.urls import reverse
from django.utils.timezone import now

# Allauth signals
from allauth.socialaccount.signals import social_account_updated, social_account_added
from allauth.account.signals import user_signed_up

# Google API imports
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dateutil import parser

# Import all necessary models
from .models import GoogleWebhookChannel, OutlookWebhookSubscription, UserProfile

logger = logging.getLogger(__name__)

@receiver(social_account_added)
@receiver(social_account_updated)
def setup_webhooks_on_login(sender, request, sociallogin, **kwargs):
    """
    Handles automated webhook registration for BOTH Google and Microsoft.
    """
    user = sociallogin.user
    provider = sociallogin.account.provider

    if not settings.DEBUG:
        return

    logger.info(f"Signal received for '{provider}' user: {user.username}. Setting up webhook.")

    # --- THIS IS THE CRITICAL FIX ---
    # We are going back to a simple, hardcoded URL.
    # You MUST ensure this URL matches the one from your ngrok terminal.
    try:
        # Get the ngrok URL from the environment variable defined in your settings
        public_url = settings.NGROK_URL
        if not public_url:
            raise ValueError("NGROK_URL is not set in your environment.")
        logger.info(f"Using ngrok URL from settings: {public_url}")
    except (AttributeError, ValueError) as e:
        logger.error(f"FATAL: NGROK_URL not configured in settings.py. Aborting webhook setup. Error: {e}")
        return
    # --------------------------------

    # --- GOOGLE LOGIC ---
    if provider == 'google':
        try:
            token = sociallogin.token
            credentials = Credentials(
                token=token.token, refresh_token=token.token_secret,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=sociallogin.token.app.client_id, client_secret=sociallogin.token.app.secret
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
            GoogleWebhookChannel.objects.create(user=user, channel_id=response['id'], resource_id=response['resourceId'])
            logger.info(f"SUCCESS: Automatically registered Google webhook for {user.username}!")
        except Exception as e:
            logger.error(f"FATAL: Could not register Google webhook: {e}", exc_info=True)

    # --- MICROSOFT LOGIC ---
    elif provider == 'microsoft':
        try:
            token = sociallogin.token.token
            graph_api_endpoint = 'https://graph.microsoft.com/v1.0/subscriptions'
            headers = {'Authorization': f'Bearer {token}'}
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
            
            response = requests.post(graph_api_endpoint, headers=headers, json=subscription_payload)
            response.raise_for_status()
            subscription_data = response.json()
            OutlookWebhookSubscription.objects.create(
                user=user,
                subscription_id=subscription_data['id'],
                expiration_datetime=parser.parse(subscription_data['expirationDateTime'])
            )
            logger.info(f"SUCCESS: Automatically registered Outlook webhook for {user.username}!")
        except Exception as e:
            logger.error(f"FATAL: Could not register Outlook webhook: {e}", exc_info=True)

@receiver(user_signed_up)
def create_profile_on_social_signup(request, user, **kwargs):
    UserProfile.objects.get_or_create(user=user)