# scheduler_app/models.py

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# Correctly import the SocialAccount model
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
    source = models.CharField(max_length=50, choices=[('google', 'Google'), ('microsoft', 'Microsoft'), ('local', 'Local')], default='local', db_index=True)
    event_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    
    # This is the correct reference to the SocialAccount model
    social_account = models.ForeignKey('socialaccount.SocialAccount', on_delete=models.CASCADE, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [ models.UniqueConstraint(fields=['social_account', 'event_id'], name='unique_event_per_social_account') ]

    def __str__(self):
        return f"{self.title} ({self.source}) on {self.date} for {self.user.username}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    def __str__(self): return f"Profile of {self.user.username}"

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    UserProfile.objects.get_or_create(user=instance)


class GoogleWebhookChannel(models.Model):
    # THIS IS THE FIX: Make the field nullable to allow migrations on existing databases.
    social_account = models.OneToOneField(SocialAccount, on_delete=models.CASCADE, null=True, blank=True)
    channel_id = models.CharField(max_length=255, unique=True)
    resource_id = models.CharField(max_length=255)
    expiration = models.DateTimeField(blank=True, null=True)
    def __str__(self): return f"Google Channel for {self.social_account}"


class OutlookWebhookSubscription(models.Model):
    # THIS IS THE FIX: Make the field nullable to allow migrations on existing databases.
    social_account = models.OneToOneField(SocialAccount, on_delete=models.CASCADE, null=True, blank=True)
    subscription_id = models.CharField(max_length=255, unique=True)
    expiration_datetime = models.DateTimeField()
    def __str__(self): return f"Outlook Sub for {self.social_account}"


class SyncedCalendar(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    provider = models.CharField(max_length=50, choices=[('google', 'Google'), ('microsoft', 'Microsoft')])
    calendar_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    # THIS IS THE FIX: Make the field nullable to allow migrations on existing databases.
    social_account = models.ForeignKey(SocialAccount, on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        unique_together = ('user', 'provider', 'calendar_id')

    def __str__(self):
        return f"{self.name} ({self.provider}) for {self.user.username}"