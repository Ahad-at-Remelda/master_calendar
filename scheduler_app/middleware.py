# scheduler_app/middleware.py

from django.utils import timezone
import pytz

class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # This is a simple example. In a real application, you might store
        # the user's preferred timezone in their UserProfile model.
        # For now, we'll use a common timezone like 'America/New_York'.
        # You can change this string to your local timezone for testing.
        # A list of timezones can be found here: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
        
        user_timezone = 'Asia/Karachi' # <-- EXAMPLE: Changed from America/New_York

        if request.user.is_authenticated:
            try:
                # Activate the user's timezone. All subsequent template rendering
                # and date/time operations for this request will use this timezone.
                timezone.activate(pytz.timezone(user_timezone))
            except pytz.UnknownTimeZoneError:
                # If the timezone is invalid, fall back to the default.
                timezone.deactivate()
        else:
            # Deactivate to use the default timezone from settings.py for logged-out users.
            timezone.deactivate()

        response = self.get_response(request)
        return response