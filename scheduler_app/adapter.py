# scheduler_app/adapter.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.urls import reverse
from datetime import date
import logging

logger = logging.getLogger(__name__)

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    
    def get_login_redirect_url(self, request):
        """
        This is called when a user LOGS IN using a social account.
        """
        path = reverse('redirect_after_login')
        logger.info(f"Adapter: Redirecting after SOCIAL LOGIN to: {path}")
        return path

    def get_connect_redirect_url(self, request, socialaccount):
        """
        THIS IS THE CRITICAL FIX.
        This is called when a user who is ALREADY LOGGED IN connects a new social account.
        """
        path = reverse('redirect_after_login')
        logger.info(f"Adapter: Redirecting after SOCIAL CONNECT to: {path}")
        return path

    def pre_social_login(self, request, sociallogin):
        """
        This code handles linking accounts and is already working correctly.
        """
        # If the user is already logged in, we are in a 'connect' flow.
        # allauth will handle this automatically.
        if request.user.is_authenticated:
            return

        # Handle linking a new social login to an existing user by email.
        email = sociallogin.account.extra_data.get('email')
        if email:
            try:
                from django.contrib.auth.models import User
                user = User.objects.get(email__iexact=email)
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass
            
            
    def get_login_redirect_url(self, request):
        return reverse('redirect_after_login')

    def get_connect_redirect_url(self, request, socialaccount):
        return reverse('redirect_after_login')