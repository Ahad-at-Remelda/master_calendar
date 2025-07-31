# scheduler_app/management/commands/register_google_webhook.py

import uuid
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialToken
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from scheduler_app.models import GoogleWebhookChannel

class Command(BaseCommand):
    help = 'Registers a webhook with Google Calendar to watch for changes.'

    def add_arguments(self, parser):
        parser.add_argument('ngrok_url', type=str, help='The base public URL provided by ngrok.')
        parser.add_argument('username', type=str, help='The username of the user whose calendar to watch.')

    def handle(self, *args, **options):
        ngrok_url = options['ngrok_url'].rstrip('/')
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
            token = SocialToken.objects.get(account__user=user, account__provider='google')
        except (User.DoesNotExist, SocialToken.DoesNotExist):
            self.stdout.write(self.style.ERROR(f"No valid user or Google token found for username '{username}'"))
            return

        # --- THIS IS THE CRITICAL FIX ---
        # We now correctly build the credentials object from the user's token
        credentials = Credentials(
            token=token.token,
            refresh_token=token.token_secret,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=token.app.client_id,
            client_secret=token.app.secret
        )
        # ---------------------------------

        service = build('calendar', 'v3', credentials=credentials)
        
        webhook_url = ngrok_url + reverse('google_webhook')
        channel_uuid = str(uuid.uuid4())
        
        watch_request_body = {
            'id': channel_uuid,
            'type': 'web_hook',
            'address': webhook_url
        }

        try:
            # First, stop any old channels for this user to avoid duplicates
            old_channel = GoogleWebhookChannel.objects.filter(user=user).first()
            if old_channel:
                self.stdout.write(self.style.WARNING(f"Attempting to stop old channel: {old_channel.channel_id}"))
                service.channels().stop(body={'id': old_channel.channel_id, 'resourceId': old_channel.resource_id}).execute()
                old_channel.delete()
                self.stdout.write(self.style.SUCCESS(f"Stopped and deleted old webhook channel for {username}."))

            # Now, register the new one
            response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
            
            # Save the new channel info to our database
            GoogleWebhookChannel.objects.create(
                user=user,
                channel_id=response['id'],
                resource_id=response['resourceId']
            )
            
            self.stdout.write(self.style.SUCCESS('Successfully registered new webhook!'))
            self.stdout.write(f"Channel ID: {response.get('id')}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to register webhook: {e}"))