# scheduler_app/routing.py
from django.urls import re_path
from .consumers import CalendarConsumer

websocket_urlpatterns = [
    re_path(r'ws/calendar/$', CalendarConsumer.as_asgi()),
]
