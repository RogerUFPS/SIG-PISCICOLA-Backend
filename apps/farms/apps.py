from django.apps import AppConfig


class FarmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.farms"
    label = "farms"

    def ready(self):
        import apps.farms.signals
