# master_calendar/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('admin/', admin.site.urls),

    # This line MUST come before the 'accounts' line
    path('', include('scheduler_app.urls')),

    # This line tells Django to use ALL of allauth's views for login, logout, etc.
    path('accounts/', include('allauth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)