# farms/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Farm, FarmRole, FarmRoleAppPermission
from .modules import MODULES

DEFAULT_ROLE_MODULES = {
    "Operario": ("fish_health",),
    "Biólogo": (
        "fish_health",
        "water_quality_monitoring",
        "production_batches",
        "production_cycles",
        "farm_events",
        "feeding_management",
        "harvest_management",
        "pond_management",
    ),
    "Administrador de Granja": tuple(MODULES),
}


@receiver(post_save, sender=Farm)
def create_default_roles(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.core.signals import audit_bulk_create

    roles = [
        FarmRole(farm=instance, name=name)
        for name in DEFAULT_ROLE_MODULES
    ]
    audit_bulk_create(FarmRole, roles)
    grants = [
        FarmRoleAppPermission(
            role=role,
            module=module,
            can_view=True,
            can_create=module not in ("alerts", "audit_logs"),
            can_update=module not in ("alerts", "audit_logs"),
            can_delete=module not in ("alerts", "audit_logs"),
        )
        for role in roles
        for module in DEFAULT_ROLE_MODULES[role.name]
    ]
    audit_bulk_create(FarmRoleAppPermission, grants)
