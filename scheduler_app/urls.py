# scheduler_app/urls.py

# scheduler_app/urls.py
# scheduler_app/urls.py
from django.urls import path
from . import views
from datetime import date
from django.shortcuts import redirect
from rest_framework.authtoken.views import obtain_auth_token


today = date.today()
calendar_redirect_view = lambda request: redirect('calendar', year=today.year, month=today.month)

urlpatterns = [
    path('', calendar_redirect_view, name='home'),
    path('calendar/<int:year>/<int:month>/', views.calendar_view, name='calendar'),
    # ... your other app-specific URLs ...
    path('add/', views.add_event, name='add_event'),
    path('api/event/<int:event_id>/', views.event_detail_api, name='event_detail_api'),
    path('google-webhook/', views.google_webhook_receiver, name='google_webhook'),
    path('outlook-webhook/', views.outlook_webhook_receiver, name='outlook_webhook'),
    path('disconnect/<int:account_id>/', views.disconnect_social_account, name='disconnect_social_account'),
    #path('select-calendars/<str:provider>/', views.select_calendars_view, name='select_calendars'),
    #path('save-calendar-selection/<str:provider>/', views.save_calendar_selection_view, name='save_calendar_selection'),
    path('redirect-after-login/', views.redirect_after_login, name='redirect_after_login'),
    path('api/token-login/', obtain_auth_token, name='api_token_auth'),

]
# # scheduler_app/urls.py

# from django.urls import path
# from . import views

# urlpatterns = [
#     path('', views.home, name='home'),

#     # Calendar display
#     path('calendar/<int:year>/<int:month>/', views.calendar_view, name='calendar'),

#     # --- THIS IS THE NEW, SIMPLIFIED URL ---
#     # The URL no longer needs year, month, or day
#     path('add/', views.add_event, name='add_event'),
#     # ---------------------------------------
#     path('api/event/<int:event_id>/', views.event_detail_api, name='event_detail_api'),
#     # API endpoint for adding an event
#     # Webhook endpoint from Google
#     path('google-webhook/', views.google_webhook_receiver, name='google_webhook'),

#     # Your other debug/testing URLs can remain
#     path("trigger-webhook/", views.trigger_webhook, name="trigger_webhook"),
#     path('api/sync-events/', views.sync_events, name='sync_events'),
#     path('outlook-webhook/', views.outlook_webhook_receiver, name='outlook_webhook'),
#     path('sync-outlook/', views.sync_outlook, name='sync_outlook_events'),

# ]