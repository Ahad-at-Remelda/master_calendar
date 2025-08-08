 #She following views are not strictly necessary for production but can be useful for debugging or testing.
# The other helper/debug views are not needed for production but can be kept for testing
# ... (start_google_calendar_watch, trigger_webhook, sync_events) ...
# def start_google_calendar_watch(user, credentials):
#     service = build('calendar', 'v3', credentials=credentials)
#     channel_id = str(uuid.uuid4())
#     webhook_url = "https://79c15e1980a4.ngrok-free.app/google-webhook/"

#     body = {
#         "id": channel_id,
#         "type": "web_hook",
#         "address": webhook_url,
#         "token": "some_random_token_123",
#         "params": {
#             "ttl": "604800"
#         }
#     }

#     response = service.events().watch(calendarId='primary', body=body).execute()

#     GoogleWebhookChannel.objects.update_or_create(
#         user=user,
#         defaults={
#             'channel_id': channel_id,
#             'resource_id': response.get("resourceId"),
#             'expiration': datetime.datetime.fromtimestamp(int(response["expiration"]) / 1000.0),
#         }
#     )

#     logger.info(f"Google Calendar watch started for user {user.username}")


# @login_required
# def trigger_webhook(request):
#     from scheduler_app.signals import setup_google_webhook_on_login
#     from allauth.socialaccount.models import SocialAccount

#     try:
#         account = SocialAccount.objects.get(user=request.user, provider='google')
#         setup_google_webhook_on_login(sender=None, request=request, sociallogin=type('obj', (object,), {
#             'user': request.user,
#             'token': account.socialtoken_set.first(),
#             'account': account
#         })())
#         return HttpResponse("✅ Webhook manually triggered.")
#     except Exception as e:
#         return HttpResponse(f"❌ Failed to trigger webhook: {e}", status=500)


# @login_required
# def sync_events(request):
#     try:
#         token = SocialToken.objects.get(account__user=request.user, account__provider='google')
#         credentials = Credentials(
#             token=token.token,
#             refresh_token=token.token_secret,
#             token_uri='https://oauth2.googleapis.com/token',
#             client_id=token.app.client_id,
#             client_secret=token.app.secret
#         )
#         if credentials.expired and credentials.refresh_token:
#             credentials.refresh(Request())
#             token.token = credentials.token
#             token.save()

#         service = build('calendar', 'v3', credentials=credentials)
#         now = datetime.datetime.utcnow().isoformat() + 'Z'
#         events_result = service.events().list(
#             calendarId='primary',
#             timeMin=now,
#             singleEvents=True,
#             orderBy='startTime'
#         ).execute()

#         for event in events_result.get('items', []):
#             event_id = event.get('id')
#             summary = event.get('summary', '')
#             description = event.get('description', '')
#             start_time = event['start'].get('dateTime') or event['start'].get('date')
#             end_time = event['end'].get('dateTime') or event['end'].get('date')

#             Event.objects.update_or_create(
#                 google_event_id=event_id,
#                 user=request.user,
#                 defaults={
#                     'title': summary,
#                     'description': description,
#                     'start_time': start_time,
#                     'end_time': end_time,
#                     'date': start_time.date(),  

#                 }
#             )

#         return JsonResponse({'status': 'success'})
#     except Exception as e:
#         logger.error(f"Manual sync failed: {e}", exc_info=True)
#         return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# # @login_required
# # def event_detail_api(request, event_id):
# #     """
# #     This is an API endpoint that returns the details of a single event as JSON.
# #     """
# #     # Find the event by its ID, ensuring it belongs to the logged-in user for security.
# #     event = get_object_or_404(Event, id=event_id, user=request.user)

# #     # Format the start and end times for display
# #     start_time = event.start_time.strftime('%A, %B %d, %Y at %I:%M %p') if event.start_time else "All-day"
# #     end_time = event.end_time.strftime('%A, %B %d, %Y at %I:%M %p') if event.end_time else ""

# #     # Prepare the data to be sent as JSON
# #     data = {
# #         'id': event.id,
# #         'title': event.title,
# #         'description': event.description,
# #         'date': event.date.strftime('%Y-%m-%d'),
# #         'start_time': start_time,
# #         'end_time': end_time,
# #         'location': event.location,
# #         'meeting_link': event.meeting_link,
# #         'source': event.source,
# #     }
# #     return JsonResponse(data)

# @login_required
# def sync_outlook_events(request):
#     try:
#         token = SocialToken.objects.get(account__user=request.user, account__provider='microsoft')
#         headers = {'Authorization': f'Bearer {token.token}'}
#         graph_api_endpoint = 'https://graph.microsoft.com/v1.0/me/events'
#         response = requests.get(graph_api_endpoint, headers=headers)
#         response.raise_for_status()
#         outlook_events_data = response.json().get('value', [])

#         for event_data in outlook_events_data:
#             event_id = event_data.get('id')
#             if not event_id:
#                 continue

#             start_raw = event_data.get('start', {}).get('dateTime')
#             if not start_raw:
#                 continue

#             start_time = parser.parse(start_raw)
#             end_time = parser.parse(event_data.get('end', {}).get('dateTime')) if event_data.get('end') else None

#             Event.objects.update_or_create(
#                 user=request.user,
#                 event_id=event_id,
#                 defaults={
#                     'title': event_data.get('subject', 'No Title'),
#                     'description': event_data.get('bodyPreview', ''),
#                     'date': start_time.date(),
#                     'start_time': start_time,
#                     'end_time': end_time,
#                     'source': 'outlook',
#                     'etag': event_data.get('@odata.etag', ''),
#                     'location': event_data.get('location', {}).get('displayName', ''),
#                 }
#             )

#         return JsonResponse({'status': 'success', 'count': len(outlook_events_data)})
#     except Exception as e:
#         logger.error(f"Manual Outlook sync failed: {e}", exc_info=True)
#         return JsonResponse({'status': 'error', 'message': str(e)}, status=500)



# # # views.py
# # import requests
# # import logging
# # from allauth.socialaccount.models import SocialToken
# # from django.contrib.auth.decorators import login_required
# # from django.http import JsonResponse

# # # Set up logger
# # logger = logging.getLogger(__name__)

# @login_required
# def sync_outlook(request):
#     user = request.user

#     logger.info("🔔 Received request to sync Outlook for user: %s", user.username)

#     try:
#         token = SocialToken.objects.get(account__user=user, account__provider='microsoft')
#         access_token = token.token
#         logger.info("✅ Access token retrieved: %s", access_token)

#     except SocialToken.DoesNotExist:
#         logger.error("❌ No SocialToken found for user: %s", user.username)
#         return JsonResponse({'status': 'error', 'message': 'SocialToken matching query does not exist.'})

#     # Request to Microsoft Graph API to get calendar events
#     graph_url = "https://graph.microsoft.com/v1.0/me/events"
#     headers = {
#         'Authorization': f'Bearer {access_token}',
#         'Accept': 'application/json'
#     }

#     logger.info("📤 Sending request to Microsoft Graph API: %s", graph_url)
#     logger.debug("📨 Request headers: %s", headers)

#     response = requests.get(graph_url, headers=headers)

#     logger.info("📥 Received response status: %s", response.status_code)
#     logger.debug("📦 Response content: %s", response.text)

#     if response.status_code == 200:
#         events = response.json().get('value', [])
#         logger.info("✅ Events fetched successfully: %d events found", len(events))
#         return JsonResponse({'status': 'success', 'events': events})

#     logger.error("❌ Failed to fetch events from Microsoft Graph: %s", response.text)
#     return JsonResponse({'status': 'error', 'message': 'Failed to fetch events', 'details': response.text})
