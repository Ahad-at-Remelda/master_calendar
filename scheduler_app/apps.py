from django.apps import AppConfig

class SchedulerAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduler_app'

    def ready(self):
        import scheduler_app.templatetags.custom_filters
