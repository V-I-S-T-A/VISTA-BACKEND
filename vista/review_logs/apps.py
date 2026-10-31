from django.apps import AppConfig


class ReviewLogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "review_logs"

    def ready(self):
        from . import signals  # noqa: F401
