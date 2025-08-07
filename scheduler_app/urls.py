# scheduler_app/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    # Calendar display
    path('calendar/<int:year>/<int:month>/', views.calendar_view, name='calendar'),

    # --- THIS IS THE NEW, SIMPLIFIED URL ---
    # The URL no longer needs year, month, or day
    path('add/', views.add_event, name='add_event'),
    # ---------------------------------------
    path('api/event/<int:event_id>/', views.event_detail_api, name='event_detail_api'),
    # API endpoint for adding an event
    # Webhook endpoint from Google
    path('google-webhook/', views.google_webhook_receiver, name='google_webhook'),

    # Your other debug/testing URLs can remain
    path("trigger-webhook/", views.trigger_webhook, name="trigger_webhook"),
    path('api/sync-events/', views.sync_events, name='sync_events'),
    path('outlook-webhook/', views.outlook_webhook_receiver, name='outlook_webhook'),
    path('sync-outlook/', views.sync_outlook, name='sync_outlook_events'),

]