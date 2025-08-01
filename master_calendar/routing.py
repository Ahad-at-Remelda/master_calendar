# master_calendar/routing.py

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from scheduler_app.consumers import CalendarConsumer  # adjust if needed
from django.urls import re_path

application = ProtocolTypeRouter({
    "websocket": AuthMiddlewareStack(
        URLRouter([
            re_path(r"ws/calendar/$", CalendarConsumer.as_asgi()),
        ])
    ),
})
