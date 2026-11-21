import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def add_legacy_role_permissions(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    RoleAppPermission = apps.get_model("accounts", "RoleAppPermission")
    app_labels = [
        app_config.label
        for app_config in apps.get_app_configs()
        if app_config.name.startswith("apps.") and app_config.label != "accounts"
    ]
    for role in Role.objects.exclude(name="Admin").iterator():
        RoleAppPermission.objects.bulk_create(
            [
                RoleAppPermission(
                    role_id=role.pk,
                    app=app_label,
                    can_view=True,
                    can_create=app_label != "species",
                    can_edit=app_label != "species",
                    can_delete=app_label != "species",
                )
                for app_label in app_labels
            ],
            ignore_conflicts=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_rename_invitation_farm_id_51f0ae_idx_invitation_farm_id_ececd5_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoleAppPermission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("app", models.CharField(max_length=50)),
                ("can_view", models.BooleanField(default=False)),
                ("can_create", models.BooleanField(default=False)),
                ("can_edit", models.BooleanField(default=False)),
                ("can_delete", models.BooleanField(default=False)),
                (
                    "role",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="app_permissions",
                        to="accounts.role",
                    ),
                ),
            ],
            options={"db_table": "role_app_permission"},
        ),
        migrations.CreateModel(
            name="UserSession",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("last_activity", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="jwt_sessions",
                        to="accounts.user",
                    ),
                ),
            ],
            options={"db_table": "user_session"},
        ),
        migrations.AddConstraint(
            model_name="roleapppermission",
            constraint=models.UniqueConstraint(
                fields=("role", "app"),
                name="unique_role_app_permission",
            ),
        ),
        migrations.AddIndex(
            model_name="usersession",
            index=models.Index(
                fields=["user", "revoked_at"],
                name="user_sessio_user_id_5efccf_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="usersession",
            index=models.Index(
                fields=["expires_at"],
                name="user_sessio_expires_85bda6_idx",
            ),
        ),
        migrations.RunPython(add_legacy_role_permissions, migrations.RunPython.noop),
    ]
