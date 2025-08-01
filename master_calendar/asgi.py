# master_calendar/asgi.py

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import scheduler_app.routing # Import the routing file from your app

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "master_calendar.settings")

# This is the standard and correct way to configure your ASGI application
application = ProtocolTypeRouter({
    # Django's HTTP handling
    "http": get_asgi_application(),

    # WebSocket handling
    "websocket": AuthMiddlewareStack(
        URLRouter(
            # We get the WebSocket URL patterns from your app's routing file
            scheduler_app.routing.websocket_urlpatterns
        )
    ),
})