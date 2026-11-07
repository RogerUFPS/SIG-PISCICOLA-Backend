# farms/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from .enums import FarmPermission
from .models import Farm, FarmRole

DEFAULT_ROLES = [
    {
        "name": "Operario",
        "permissions": int(FarmPermission.MANAGE_REVIEWS),
    },
    {
        "name": "Biólogo",
        "permissions": int(
            FarmPermission.MANAGE_REVIEWS
            | FarmPermission.MANAGE_CYCLE
            | FarmPermission.MANAGE_POND
        ),
    },
    {
        "name": "Administrador de Granja",
        "permissions": int(FarmPermission.ALL),
    },
]


@receiver(post_save, sender=Farm)
def create_default_roles(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.core.signals import audit_bulk_create

    audit_bulk_create(
        FarmRole,
        [
            FarmRole(farm=instance, name=role["name"], permissions=role["permissions"])
            for role in DEFAULT_ROLES
        ]
    )
