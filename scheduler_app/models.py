# scheduler_app/models.py

from django.db import models
from django.contrib.auth.models import User

class Event(models.Model):
    # This model is correct, but ensure user can be null for public events
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField()

    def __str__(self):
        return f"{self.title} on {self.date}"

class GoogleWebhookChannel(models.Model):
    # --- THIS IS THE CRITICAL FIX ---
    # We are changing this to a OneToOneField for a cleaner, more robust relationship.
    # The related_name is also updated for clarity.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="google_webhook_channel")
    # --------------------------------
    channel_id = models.CharField(max_length=255, unique=True)
    resource_id = models.CharField(max_length=255)
    token = models.CharField(max_length=255, blank=True, null=True)
    expiration = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Webhook for {self.user.username} ({self.channel_id})"