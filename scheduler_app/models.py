# scheduler_app/models.py

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError

# Use string import for SocialAccount to avoid import cycle in migrations
# We'll reference it via integer field storing SocialAccount.id in webhook models.

class Event(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField()
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    meeting_link = models.URLField(max_length=500, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    is_recurring = models.BooleanField(default=False)

    source = models.CharField(
        max_length=50,
        choices=[
            ('google', 'Google'),
            ('microsoft', 'Microsoft'),
            ('teams', 'Teams'),
            ('local', 'Local'),
        ],
        default='local'
    )

    # remote event id from provider (may not be globally unique across users)
    event_id = models.CharField(max_length=255, null=True, blank=True)
    etag = models.CharField(max_length=255, blank=True, null=True)

    # link to a specific synced calendar (optional)
    synced_calendar = models.ForeignKey('SyncedCalendar', on_delete=models.SET_NULL, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} on {self.date}"

    def clean(self):
        if self.user and self.start_time and self.end_time:
            overlapping_events = Event.objects.filter(
                user=self.user,
                date=self.date
            ).exclude(id=self.id).filter(
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            )
            if overlapping_events.exists():
                raise ValidationError("This time slot overlaps with another event for the same user.")

    class Meta:
        # THIS IS THE CRITICAL FIX:
        # We replace unique_together with a more flexible constraint.
        # This ensures that for external events (Google/Outlook), the combination
        # of user, source, and event_id is unique. It correctly allows multiple
        # local events where event_id is NULL.
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'source', 'event_id'],
                name='unique_external_event_for_user'
            )
        ]




class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    watch_enabled = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile of {self.user.username}"

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    UserProfile.objects.get_or_create(user=instance)

# --- Google Webhook Channel ---
class GoogleWebhookChannel(models.Model):
    social_account_id = models.PositiveIntegerField(
        help_text="allauth SocialAccount.id",
        null=True,  # allow nulls for existing rows
        blank=True
    )
    channel_id = models.CharField(max_length=255)
    resource_id = models.CharField(max_length=255)
    token = models.CharField(max_length=255, blank=True, null=True)
    expiration = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = (('social_account_id', 'channel_id'),)

    def __str__(self):
        return f"Google Channel {self.channel_id} (social_account_id={self.social_account_id})"


class OutlookWebhookSubscription(models.Model):
    social_account_id = models.PositiveIntegerField(
        help_text="allauth SocialAccount.id",
        null=True,  # allow nulls for existing rows
        blank=True
    )
    subscription_id = models.CharField(max_length=255)
    expiration_datetime = models.DateTimeField()

    class Meta:
        unique_together = (('social_account_id', 'subscription_id'),)

    def __str__(self):
        return f"Outlook Sub {self.subscription_id} (social_account_id={self.social_account_id})"


class SyncedCalendar(models.Model):
    """
    Track each specific calendar a user has chosen to sync.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.CharField(max_length=50, choices=[('google', 'Google'), ('microsoft', 'Microsoft')])
    calendar_id = models.CharField(max_length=255)  # provider's calendar id
    name = models.CharField(max_length=255)
    is_sync_enabled = models.BooleanField(default=True)
    social_account_id = models.PositiveIntegerField(help_text="allauth SocialAccount.id", null=True, blank=True)
    
    class Meta:
        unique_together = ('user', 'provider', 'calendar_id')

    def __str__(self):
        return f"{self.name} ({self.provider}) for {self.user.username}"
