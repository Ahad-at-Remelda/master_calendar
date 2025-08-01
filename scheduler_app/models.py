# scheduler_app/models.py

from django.db import models
from django.contrib.auth.models import User

class Event(models.Model):
    # --- THIS IS THE NEW LINE ---
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    # --------------------------
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField()

    def __str__(self):
        return f"{self.title} on {self.date}"

# Your GoogleWebhookChannel model stays the same
class GoogleWebhookChannel(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="google_webhook_channel")
    channel_id = models.CharField(max_length=255, unique=True)
    resource_id = models.CharField(max_length=255)

    def __str__(self):
        return f"Webhook for {self.user.username}"