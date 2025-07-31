from django.db import models
from django.contrib.auth.models import User # Or your custom user model

class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField()

    def __str__(self):
        return f"{self.title} on {self.date}"



# NEW MODEL to store webhook information
class GoogleWebhookChannel(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="google_webhook_channel")
    channel_id = models.CharField(max_length=255, unique=True)
    resource_id = models.CharField(max_length=255)
    # You could also store expiration date, etc.

    def __str__(self):
        return f"Webhook for {self.user.username}"

