from django.db import migrations, models


def revoke_duplicate_active_sessions(apps, schema_editor):
    UserSession = apps.get_model("accounts", "UserSession")
    database = schema_editor.connection.alias
    active_sessions = UserSession.objects.using(database).filter(
        revoked_at__isnull=True
    ).order_by("user_id", "-last_activity", "pk")
    last_user_id = None
    for session in active_sessions.iterator():
        if session.user_id == last_user_id:
            UserSession.objects.using(database).filter(pk=session.pk).update(
                revoked_at=session.last_activity
            )
        else:
            last_user_id = session.user_id


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_remove_roleapppermission_unique_role_app_permission_and_more"),
    ]

    operations = [
        migrations.RunPython(
            revoke_duplicate_active_sessions,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="usersession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("revoked_at__isnull", True)),
                fields=("user",),
                name="unique_active_user_session",
            ),
        ),
    ]
