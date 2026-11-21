from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_alter_alert_source_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("Health", "Salud"),
                    ("HealthStat", "Diagnóstico sanitario"),
                    ("Stock", "Stock"),
                    ("Ambiental", "Ambiental"),
                    ("Control", "Control"),
                    ("Feeding", "Alimentación"),
                    ("Sale", "Venta"),
                ],
                max_length=20,
            ),
        ),
    ]
