from django.apps import AppConfig


class FeedingConfig(AppConfig):
    name = "apps.feeding"

    def ready(self):
        import apps.feeding.signals
