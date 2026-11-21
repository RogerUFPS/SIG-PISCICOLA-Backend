from django.utils import timezone

from .models import Product, Supplier


def soft_delete(instance) -> None:
    instance.deleted_at = timezone.now()
    instance.save(update_fields=["deleted_at"])
