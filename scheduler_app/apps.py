# scheduler_app/apps.py

import sys
import uuid
import logging
from django.apps import AppConfig
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

class SchedulerAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduler_app'

    def ready(self):
        # Only run this logic when starting the main server in DEBUG mode
        is_running_server = any(cmd in sys.argv for cmd in ['runserver', 'daphne'])
        if not is_running_server or not settings.DEBUG:
            return

        # Import everything we need here, inside the method
        from pyngrok import ngrok
        from django.contrib.auth.models import User
        from allauth.socialaccount.models import SocialToken
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from .models import GoogleWebhookChannel

        try:
            # Get the public URL from the running ngrok tunnel
            public_url = ngrok.connect(8000).public_url
            logger.info(f"Ngrok tunnel is running at: {public_url}")

            # --- Development Shortcut ---
            # For development, we'll just register the webhook for the first superuser.
            # In production, you would have a different system for this.
            user_to_watch = User.objects.filter(is_superuser=True).first()
            if not user_to_watch:
                logger.warning("No superuser found. Skipping automatic webhook registration.")
                return

            logger.info(f"Found user to watch: {user_to_watch.username}")
            
            token = SocialToken.objects.get(account__user=user_to_watch, account__provider='google')
            
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
            
            watch_request_body = {
                'id': channel_uuid,
                'type': 'web_hook',
                'address': webhook_url
            }

            # Stop any old channels first
            old_channel = GoogleWebhookChannel.objects.filter(user=user_to_watch).first()
            if old_channel:
                service.channels().stop(body={'id': old_channel.channel_id, 'resourceId': old_channel.resource_id}).execute()
                old_channel.delete()
                logger.info(f"Stopped and deleted old webhook for {user_to_watch.username}.")

            # Register the new one
            response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
            GoogleWebhookChannel.objects.create(user=user_to_watch, channel_id=response['id'], resource_id=response['resourceId'])
            
            logger.info(f"SUCCESS: Automatically registered webhook for {user_to_watch.username}!")

        except Exception as e:
            logger.error(f"Could not automatically register webhook on startup: {e}")