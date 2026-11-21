from django.apps import AppConfig


class PurchaseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.purchases"
    label = "purchases"

    def ready(self):
        import apps.purchases.signals
