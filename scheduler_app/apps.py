# scheduler_app/apps.py

from django.apps import AppConfig

class SchedulerAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduler_app'

    def ready(self):
        """
        This method is called once when the Django app is fully loaded.
        This is the correct, modern place to import signals.
        """
        import scheduler_app.signals