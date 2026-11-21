from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("batch", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="batch",
            name="origin_type",
            field=models.CharField(
                choices=[
                    ("harvest_classification", "Harvest Classification"),
                    ("purchase_detail", "Purchase Detail"),
                    ("batch_split", "Batch Split"),
                    ("initial", "Initial"),
                ],
                default="initial",
                max_length=50,
            ),
        ),
    ]
