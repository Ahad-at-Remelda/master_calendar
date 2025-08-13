# scheduler_app/urls.py

from django.urls import path
from . import views
from datetime import date
from django.shortcuts import redirect

today = date.today()
calendar_redirect_view = lambda request: redirect('calendar', year=today.year, month=today.month)

urlpatterns = [
    # --- CORE CALENDAR URLs ---
    path('', calendar_redirect_view, name='home'),
    path('calendar/<int:year>/<int:month>/', views.calendar_view, name='calendar'),
    path('add/', views.add_event, name='add_event'),
    path('disconnect/<int:account_id>/', views.disconnect_social_account, name='disconnect_social_account'),
    path('redirect-after-login/', views.redirect_after_login, name='redirect_after_login'),

    # --- API AND WEBHOOK URLs ---
    path('api/event/<int:event_id>/', views.event_detail_api, name='event_detail_api'),
    path('google-webhook/', views.google_webhook_receiver, name='google_webhook'),
    path('outlook-webhook/', views.outlook_webhook_receiver, name='outlook_webhook'),

    # ===============================================
    # == NEW, SIMPLIFIED URLS FOR BOOKING FEATURE ==
    # ===============================================

    # This is the single, public booking page that gets shared.
    # It shows the calendar with available slots.
    path('book/<uuid:sharing_uuid>/', views.booking_view, name='booking_view'),

    # This is the confirmation page shown to the person after they select a time slot.
    path('book/<uuid:sharing_uuid>/confirm/<str:datetime_iso>/', views.confirm_booking_view, name='confirm_booking'),
    
]