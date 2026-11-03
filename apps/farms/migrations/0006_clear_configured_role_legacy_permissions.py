from django.db import migrations


def clear_configured_role_legacy_permissions(apps, schema_editor):
    FarmRole = apps.get_model("farms", "FarmRole")
    UserFarm = apps.get_model("farms", "UserFarm")

    roles = FarmRole.objects.filter(permissions_configured=True).exclude(
        permissions=0
    )
    for role in roles.iterator():
        legacy_permissions = role.permissions
        role.permissions = 0
        role.save(update_fields=["permissions"])
        UserFarm.objects.filter(
            farm_role_id=role.pk,
            permissions=legacy_permissions,
        ).update(permissions=0)


class Migration(migrations.Migration):

    dependencies = [
        ("farms", "0005_farmrole_permissions_configured"),
    ]

    operations = [
        migrations.RunPython(
            clear_configured_role_legacy_permissions,
            migrations.RunPython.noop,
        ),
    ]
