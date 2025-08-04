# # scheduler_app/apps.py

# import sys
# import uuid
# import logging
# from django.apps import AppConfig
# from django.conf import settings
# from django.urls import reverse
# from django.db import transaction

# logger = logging.getLogger(__name__)

# class SchedulerAppConfig(AppConfig):
#     default_auto_field = 'django.db.models.BigAutoField'
#     name = 'scheduler_app'

#     def ready(self):
#         """
#         This method is now confirmed to be running on server startup.
#         """
#         is_running_server = any(cmd in sys.argv for cmd in ['runserver', 'daphne'])
#         if not is_running_server or not settings.DEBUG:
#             return

#         # This waits until the server is fully ready before running our setup.
#         transaction.on_commit(self.setup_google_webhook)

#     def setup_google_webhook(self):
#         """
#         This method contains the full, automated logic to register the webhook.
#         """
#         # We import everything here to avoid startup errors.
#         from pyngrok import ngrok
#         from django.contrib.auth.models import User
#         from allauth.socialaccount.models import SocialToken
#         from google.oauth2.credentials import Credentials
#         from googleapiclient.discovery import build
#         from google.auth.transport.requests import Request
#         from .models import GoogleWebhookChannel

#         logger.info("\n\n>>>>>>>>>> SERVER READY. ATTEMPTING TO SET UP GOOGLE WEBHOOK. <<<<<<<<<<\n")

#         try:
#             # For development, we will register the webhook for the first admin user found.
#             user_to_watch = User.objects.filter(is_superuser=True).first()
#             if not user_to_watch:
#                 logger.warning("No superuser found. Skipping automatic webhook registration.")
#                 return

#             logger.info(f"Found user to watch: {user_to_watch.username}")
            
#             token = SocialToken.objects.get(account__user=user_to_watch, account__provider='google')
            
#             credentials = Credentials(
#                 token=token.token,
#                 refresh_token=token.token_secret,
#                 token_uri='https://oauth2.googleapis.com/token',
#                 client_id=token.app.client_id,
#                 client_secret=token.app.secret
#             )

#             # Refresh the token if it's expired BEFORE we try to use it.
#             if credentials.expired and credentials.refresh_token:
#                 logger.info(f"Token for {user_to_watch.username} is expired. Refreshing now...")
#                 credentials.refresh(Request())
#                 token.token = credentials.token
#                 token.save()
#                 logger.info("Token refreshed and saved successfully.")

#             # Now we have a valid credential to build the service.
#             service = build('calendar', 'v3', credentials=credentials)
            
#             # Get the public URL from ngrok.
#             public_url = ngrok.connect(8000).public_url
#             logger.info(f"Ngrok tunnel detected at: {public_url}")

#             webhook_url = public_url + reverse('google_webhook')
#             channel_uuid = str(uuid.uuid4())
            
#             watch_request_body = {
#                 'id': channel_uuid,
#                 'type': 'web_hook',
#                 'address': webhook_url
#             }

#             # Clean up any old, lingering channels for this user.
#             old_channel = GoogleWebhookChannel.objects.filter(user=user_to_watch).first()
#             if old_channel:
#                 service.channels().stop(body={'id': old_channel.channel_id, 'resourceId': old_channel.resource_id}).execute()
#                 old_channel.delete()
#                 logger.info(f"Stopped old webhook for {user_to_watch.username}.")

#             # Register the new channel with Google.
#             response = service.events().watch(calendarId='primary', body=watch_request_body).execute()
#             GoogleWebhookChannel.objects.create(user=user_to_watch, channel_id=response['id'], resource_id=response['resourceId'])
            
#             logger.info(f"\n>>>>>>>>>> SUCCESS: AUTOMATICALLY REGISTERED NEW WEBHOOK FOR {user_to_watch.username}! <<<<<<<<<<\n")

#         except SocialToken.DoesNotExist:
#              logger.warning(f"No Google token found for user '{user_to_watch.username}'. They may need to log in once to create the token.")
#         except Exception as e:
#             logger.error(f"\n>>>>>>>>>> FATAL: COULD NOT AUTOMATICALLY REGISTER WEBHOOK ON STARTUP: {e} <<<<<<<<<<\n", exc_info=True)

# scheduler_app/apps.py

from django.apps import AppConfig

class SchedulerAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduler_app'

    def ready(self):
        import scheduler_app.signals

