# scheduler_app/models.py

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError

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

    # --- THIS IS THE CRITICAL FIX FOR THE INTEGRITYERROR ---
    source = models.CharField(
        max_length=50,
        choices=[
            ('google', 'Google'),
            ('outlook', 'Outlook'),
            ('teams', 'Teams'),
            ('local', 'Local'), # Add 'local' as a valid choice
        ],
        default='local' # Make 'local' the default for new events
    )
    # --------------------------------------------------------

    # These fields are specific to synced events and should be optional
    event_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    etag = models.CharField(max_length=255, blank=True, null=True)

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

# --- Google Webhook Channel ---
class GoogleWebhookChannel(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="google_webhook_channel")
    channel_id = models.CharField(max_length=255, unique=True)
    resource_id = models.CharField(max_length=255)
    token = models.CharField(max_length=255, blank=True, null=True)
    expiration = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Webhook for {self.user.username} ({self.channel_id})"

# --- User Profile for Sync Flag ---
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    watch_enabled = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile of {self.user.username}"

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    UserProfile.objects.get_or_create(user=instance)