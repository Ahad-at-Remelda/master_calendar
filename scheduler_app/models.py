# scheduler_app/models.py

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.socialaccount.models import SocialAccount

class Event(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    date = models.DateField(db_index=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    meeting_link = models.URLField(max_length=500, blank=True, null=True)
    
    # --- THIS IS THE FIRST FIX ---
    # We add a new, special source for events booked through our app.
    SOURCE_CHOICES = [
        ('google', 'Google'),
        ('microsoft', 'Microsoft'),
        ('local', 'Local'),
        ('booked_meeting', 'Booked Meeting'), # New source
    ]
    source = models.CharField(
        max_length=50,
        choices=SOURCE_CHOICES,
        default='local',
        db_index=True
    )
    
    event_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    social_account = models.ForeignKey('socialaccount.SocialAccount', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['social_account', 'event_id'], name='unique_event_per_social_account')
        ]

    def __str__(self):
        return f"{self.title} ({self.source}) on {self.date} for {self.user.username}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    sharing_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    
    # --- THIS IS THE SECOND FIX ---
    # This field will store the user's chosen primary calendar for sending invitations.
    primary_booking_calendar = models.ForeignKey(
        SocialAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The social account to use for creating booked events and sending invitations."
    )

    def __str__(self):
        return f"Profile of {self.user.username}"

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    UserProfile.objects.get_or_create(user=instance)


class GoogleWebhookChannel(models.Model):
    social_account = models.OneToOneField(SocialAccount, on_delete=models.CASCADE, unique=True)
    channel_id = models.CharField(max_length=255, unique=True)
    resource_id = models.CharField(max_length=255)
    expiration = models.DateTimeField(blank=True, null=True)
    def __str__(self): return f"Google Channel for {self.social_account}"


class OutlookWebhookSubscription(models.Model):
    social_account = models.OneToOneField(SocialAccount, on_delete=models.CASCADE, unique=True)
    subscription_id = models.CharField(max_length=255, unique=True)
    expiration_datetime = models.DateTimeField()
    def __str__(self): return f"Outlook Sub for {self.social_account}"

