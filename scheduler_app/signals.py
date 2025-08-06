# scheduler_app/signals.py

import uuid
import logging
from django.conf import settings
from django.dispatch import receiver
from django.urls import reverse

# This is the specific signal sent by allauth after a successful social login
from allauth.socialaccount.signals import social_account_updated, social_account_added
from allauth.socialaccount.models import SocialToken, SocialAccount

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .models import GoogleWebhookChannel
from allauth.account.signals import user_signed_up
from .models import UserProfile

logger = logging.getLogger(__name__)

# We connect our function to two signals: one for new accounts, one for existing ones logging in.
@receiver(social_account_added)
@receiver(social_account_updated)
def setup_google_webhook_on_login(sender, request, sociallogin, **kwargs):
    """
    This function runs automatically every time a user logs in via a social account.
    """
    # We only care about Google accounts
    if sociallogin.account.provider != 'google':
        return

    # We only run this in DEBUG mode with a running server
    if not settings.DEBUG:
        return

    logger.info(f"Signal received for Google user: {sociallogin.user.username}. Setting up webhook.")
    
    try:
        user = sociallogin.user
        token = sociallogin.token

        credentials = Credentials(
            token=token.token,
            refresh_token=token.token_secret,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=sociallogin.token.app.client_id,
            client_secret=sociallogin.token.app.secret
        )

        service = build('calendar', 'v3', credentials=credentials)
        
        # Get the public URL from the running ngrok tunnel
        public_url =  'https://1070c35f0614.ngrok-free.app'
        logger.info(f"Ngrok tunnel detected at: {public_url}")

        webhook_url = public_url + reverse('google_webhook')
        channel_uuid = str(uuid.uuid4())
        
        watch_request_body = {
            'id': channel_uuid,
            'type': 'web_hook',
            'address': webhook_url
        }

        # Clean up any old channels for this user
        old_channel = GoogleWebhookChannel.objects.filter(user=user).first()
        if old_channel:
            service.channels().stop(body={'id': old_channel.channel_id, 'resourceId': old_channel.resource_id}).execute()
            old_channel.delete()
            logger.info(f"Stopped old webhook for {user.username}.")

        # Register the new one
        response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
        GoogleWebhookChannel.objects.create(
            user=user,
            channel_id=response['id'],
            resource_id=response['resourceId']
        )
        
        logger.info(f"SUCCESS: Automatically registered new webhook for {user.username} upon login!")

    except Exception as e:
        logger.error(f"FATAL: Could not automatically register webhook on login: {e}", exc_info=True)
        
        
@receiver(user_signed_up)
def create_profile_on_social_signup(request, user, **kwargs):
    UserProfile.objects.get_or_create(user=user)