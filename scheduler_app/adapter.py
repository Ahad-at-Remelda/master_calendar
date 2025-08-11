# scheduler_app/adapter.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Allow connecting multiple accounts.
        Just link the new account to the existing logged-in user.
        """
        if request.user.is_authenticated:
            logger.info(
                f"Linking new social account {sociallogin.account.provider} ({sociallogin.account.extra_data.get('email')}) "
                f"to user {request.user.email}"
            )
            sociallogin.connect(request, request.user)
            return

        # If logging in for the first time via social account
        email = sociallogin.account.extra_data.get('email')
        if email:
            from django.contrib.auth.models import User
            try:
                user = User.objects.get(email__iexact=email)
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass

    def get_login_redirect_url(self, request):
        return reverse('redirect_after_login')

    def get_connect_redirect_url(self, request, socialaccount):
        return reverse('redirect_after_login')
