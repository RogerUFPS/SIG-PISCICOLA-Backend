from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("farms", "0008_migrate_permission_grants"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="farmroleapppermission",
            constraint=models.UniqueConstraint(
                fields=("role", "module"),
                name="unique_farm_role_module_permission",
            ),
        ),
        migrations.AddConstraint(
            model_name="userfarmpermission",
            constraint=models.UniqueConstraint(
                fields=("user_farm", "module", "operation"),
                name="unique_user_farm_module_operation",
            ),
        ),
        migrations.RemoveField(
            model_name="farmrole",
            name="permissions",
        ),
        migrations.RemoveField(
            model_name="farmrole",
            name="permissions_configured",
        ),
        migrations.RemoveField(
            model_name="userfarm",
            name="permissions",
        ),
    ]
