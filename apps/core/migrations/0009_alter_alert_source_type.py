from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_alter_auditlog_type_source"),
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
                    ("Cycle", "Ciclo"),
                ],
                max_length=20,
            ),
        ),
    ]
