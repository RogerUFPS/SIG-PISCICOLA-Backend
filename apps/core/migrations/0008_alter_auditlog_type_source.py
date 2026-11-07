from django.db import migrations, models


def install_immutable_audit_triggers(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == "postgresql":
            cursor.execute(
                """
                CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'Audit logs are immutable';
                END;
                $$ LANGUAGE plpgsql
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER audit_log_immutable
                BEFORE UPDATE OR DELETE ON audit_log
                FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()
                """
            )
        elif schema_editor.connection.vendor == "sqlite":
            cursor.execute(
                """
                CREATE TRIGGER audit_log_immutable_update
                BEFORE UPDATE ON audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'Audit logs are immutable');
                END
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER audit_log_immutable_delete
                BEFORE DELETE ON audit_log
                BEGIN
                    SELECT RAISE(ABORT, 'Audit logs are immutable');
                END
                """
            )


def remove_immutable_audit_triggers(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        if schema_editor.connection.vendor == "postgresql":
            cursor.execute("DROP TRIGGER IF EXISTS audit_log_immutable ON audit_log")
            cursor.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")
        elif schema_editor.connection.vendor == "sqlite":
            cursor.execute("DROP TRIGGER IF EXISTS audit_log_immutable_update")
            cursor.execute("DROP TRIGGER IF EXISTS audit_log_immutable_delete")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_alter_alert_source_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditlog",
            name="type_source",
            field=models.CharField(
                choices=[
                    ("User", "User"),
                    ("UserFarm", "UserFarm"),
                    ("Farm", "Farm"),
                    ("FarmRole", "FarmRole"),
                    ("FarmRoleAppPermission", "FarmRoleAppPermission"),
                    ("Pond", "Pond"),
                    ("UserFarmPond", "UserFarmPond"),
                    ("TypeProduct", "TypeProduct"),
                    ("Product", "Product"),
                    ("PurchaseDetail", "PurchaseDetail"),
                    ("Supplier", "Supplier"),
                    ("Specie", "Specie"),
                    ("SpecieParameter", "SpecieParameter"),
                    ("SpecieFeedingReference", "SpecieFeedingReference"),
                    ("SpecieProductionReference", "SpecieProductionReference"),
                    ("Batch", "Batch"),
                    ("ProductionPlan", "ProductionPlan"),
                    ("Cycle", "Cycle"),
                    ("FeedingSchedule", "FeedingSchedule"),
                    ("FeedingPlan", "FeedingPlan"),
                    ("FeedingEvent", "FeedingEvent"),
                    ("DailyStat", "DailyStat"),
                    ("ProductUsageLog", "ProductUsageLog"),
                    ("ControlStat", "ControlStat"),
                    ("FishEvaluated", "FishEvaluated"),
                    ("HealthStat", "HealthStat"),
                    ("TreatmentPlan", "TreatmentPlan"),
                    ("TreatmentEvent", "TreatmentEvent"),
                    ("AmbientalMeasurement", "AmbientalMeasurement"),
                    ("Alert", "Alert"),
                    ("Sale", "Sale"),
                    ("InventoryMovement", "InventoryMovement"),
                    ("Harvest", "Harvest"),
                    ("HarvestClassification", "HarvestClassification"),
                    ("Client", "Client"),
                    ("Buy", "Buy"),
                    ("Invitation", "Invitation"),
                    ("BatchTransfer", "BatchTransfer"),
                    ("GradingEvent", "GradingEvent"),
                    ("SaleDetail", "SaleDetail"),
                    ("CyclePondBatch", "Cycle Pond Batch"),
                    ("PondBatch", "PondBatch"),
                    ("SpeciePondType", "SpeciePondType"),
                    ("ProductionReport", "Production Report"),
                ],
                max_length=50,
            ),
        ),
        migrations.RunPython(
            install_immutable_audit_triggers,
            remove_immutable_audit_triggers,
        ),
    ]
