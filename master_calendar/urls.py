# master_calendar/urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # This line tells Django to look at scheduler_app/urls.py for any main site URLs
    path('', include('scheduler_app.urls')), 
    
    
    # This line tells Django to handle all login/logout/signup URLs with django-allauth
    path('accounts/', include('allauth.urls')),
]