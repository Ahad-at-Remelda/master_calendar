# scheduler_app/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('calendar/<int:year>/<int:month>/', views.calendar_view, name='calendar'),
    path('add/<int:year>/<int:month>/<int:day>/', views.add_event, name='add_event'),
    
    # URL for Google to send webhook notifications to
    path('google-webhook/', views.google_webhook_receiver, name='google_webhook'),
    
]