import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack

# ✅ Configure settings before importing anything Django-related
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_calendar.settings')
django.setup()  # 🔥 This is what was missing

# ✅ Now safe to import app routing
import scheduler_app.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            scheduler_app.routing.websocket_urlpatterns
        )
    ),
})
