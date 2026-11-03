from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("feeding", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="feedingevent",
            name="planned_quantity",
            field=models.DecimalField(decimal_places=6, max_digits=14),
        ),
    ]
