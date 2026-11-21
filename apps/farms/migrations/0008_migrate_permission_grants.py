from django.db import migrations


LEGACY_MODULES = {
    1: ("fish_health", "water_quality_monitoring"),
    2: ("inventory_products", "inventory_purchases", "inventory_sales"),
    4: (
        "production_batches",
        "production_cycles",
        "farm_events",
        "feeding_management",
        "harvest_management",
        "fish_health",
        "water_quality_monitoring",
    ),
    8: (
        "pond_management",
        "production_batches",
        "production_cycles",
        "farm_events",
        "feeding_management",
        "harvest_management",
        "fish_health",
        "water_quality_monitoring",
    ),
    16: (
        "production_batches",
        "production_cycles",
        "farm_events",
        "feeding_management",
        "harvest_management",
        "fish_health",
        "water_quality_monitoring",
        "pond_management",
        "inventory_products",
        "inventory_purchases",
        "inventory_sales",
        "species_catalog",
        "farm_management",
        "alerts",
        "audit_logs",
        "user_administration",
    ),
    32: ("user_administration",),
}

LEGACY_APP_MODULES = {
    "batch": "production_batches",
    "cycle": "production_cycles",
    "events": "farm_events",
    "feeding": "feeding_management",
    "harvest": "harvest_management",
    "health": "fish_health",
    "monitoring": "water_quality_monitoring",
    "ponds": "pond_management",
    "products": "inventory_products",
    "purchases": "inventory_purchases",
    "sales": "inventory_sales",
    "species": "species_catalog",
    "farms": "farm_management",
    "core_alerts": "alerts",
    "core_auditlogs": "audit_logs",
    "farm_users": "user_administration",
}

OPERATIONS = ("view", "create", "update", "delete")


def migrate_permission_grants(apps, schema_editor):
    FarmRole = apps.get_model("farms", "FarmRole")
    FarmRolePermission = apps.get_model("farms", "FarmRoleAppPermission")
    UserFarm = apps.get_model("farms", "UserFarm")
    UserFarmPermission = apps.get_model("farms", "UserFarmPermission")
    db = schema_editor.connection.alias

    for grant in FarmRolePermission.objects.using(db).all().iterator():
        module = LEGACY_APP_MODULES.get(grant.module, grant.module)
        if module != grant.module:
            FarmRolePermission.objects.using(db).filter(pk=grant.pk).update(
                module=module
            )

    for role in FarmRole.objects.using(db).all().iterator():
        modules = set()
        stored = role.permissions
        if stored & 16:
            modules.update(LEGACY_MODULES[16])
        else:
            for bit, names in LEGACY_MODULES.items():
                if bit != 16 and stored & bit:
                    modules.update(names)
        for module in modules:
            is_read_only = module in ("alerts", "audit_logs")
            grant, _ = FarmRolePermission.objects.using(db).get_or_create(
                role_id=role.pk,
                module=module,
                defaults={
                    "can_view": True,
                    "can_create": not is_read_only,
                    "can_update": not is_read_only,
                    "can_delete": not is_read_only,
                },
            )
            fields = [
                field
                for field in (
                    ("can_view",)
                    if is_read_only
                    else ("can_view", "can_create", "can_update", "can_delete")
                )
                if not getattr(grant, field)
            ]
            if fields:
                for field in fields:
                    setattr(grant, field, True)
                grant.save(update_fields=fields)

    for membership in UserFarm.objects.using(db).all().iterator():
        modules = set()
        stored = membership.permissions
        if stored & 16:
            modules.update(
                name
                for name in LEGACY_MODULES[16]
                if name not in ("alerts", "audit_logs")
            )
        else:
            for bit, names in LEGACY_MODULES.items():
                if bit != 16 and stored & bit:
                    modules.update(
                        name for name in names if name not in ("alerts", "audit_logs")
                    )
        UserFarmPermission.objects.using(db).bulk_create(
            [
                UserFarmPermission(
                    user_farm_id=membership.pk,
                    module=module,
                    operation=operation,
                )
                for module in modules
                for operation in OPERATIONS
            ],
            ignore_conflicts=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("farms", "0007_userfarmpermission_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrate_permission_grants,
            migrations.RunPython.noop,
        ),
    ]
