from django.db import migrations
from django.utils import timezone


def revoke_existing_active_sessions(apps, schema_editor):
    UserSession = apps.get_model("accounts", "UserSession")
    UserSession.objects.using(schema_editor.connection.alias).filter(
        revoked_at__isnull=True
    ).update(revoked_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_usersession_unique_active_user_session"),
    ]

    operations = [
        migrations.RunPython(
            revoke_existing_active_sessions,
            migrations.RunPython.noop,
        ),
    ]
