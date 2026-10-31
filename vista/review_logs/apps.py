from django.apps import AppConfig

class ReviewLogsConfig(AppConfig):
    name = "review_logs"

    def ready(self):
        from . import realtime_signals  # noqa: F401
