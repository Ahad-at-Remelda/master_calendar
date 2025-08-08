# scheduler_app/adapter.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth.models import User
import logging
from datetime import date
from django.urls import reverse

logger = logging.getLogger(__name__)

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_login_redirect_url(self, request):
        """
        This is the most powerful redirect method. It is called after ANY
        successful login, including connecting a new account.
        
        We will force it to always redirect to the current day's calendar view.
        """
        today = date.today()
        path = reverse('calendar', kwargs={'year': today.year, 'month': today.month})
        logger.info(f"Custom adapter is redirecting to: {path}")
        return path
    
    def pre_social_login(self, request, sociallogin):
        """
        This is the correct place to handle account linking.
        It runs after the user authenticates but before the login is finalized.
        """
        email = sociallogin.account.extra_data.get('email')

        # If the user is already logged in, we are in a 'connect' flow.
        if request.user.is_authenticated:
            # We don't need to do anything here. Allauth will correctly
            # connect the new social account to the logged-in user.
            logger.info(f"User '{request.user.username}' is connecting a new '{sociallogin.account.provider}' account.")
            return

        # If the user is NOT logged in, this is a 'login' flow.
        if email:
            try:
                # Try to find an existing user with this email.
                existing_user = User.objects.get(email=email)
                # If a user exists, we will link this new social account to them.
                sociallogin.connect(request, existing_user)
                logger.info(f"New social account for '{email}' connected to existing user.")
            except User.DoesNotExist:
                # This is a brand new user. Let allauth handle the signup.
                logger.info(f"No existing user for '{email}'. Proceeding with new signup.")
                pass