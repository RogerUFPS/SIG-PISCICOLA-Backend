from django.conf import settings
from django.db import models


class Unit(models.Model):
    symbol = models.CharField(max_length=20)
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "unit"
        verbose_name = "Unit"
        verbose_name_plural = "Units"

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class AuditLog(models.Model):

    class TypeSource(models.TextChoices):
        USER = "User", "User"
        USER_FARM = "UserFarm", "UserFarm"
        FARM = "Farm", "Farm"
        FARM_ROLE = "FarmRole", "FarmRole"
        POND = "Pond", "Pond"
        USER_FARM_POND = "UserFarmPond", "UserFarmPond"
        TYPE_PRODUCT = "TypeProduct", "TypeProduct"
        PRODUCT = "Product", "Product"
        PURCHASE_DETAIL = "PurchaseDetail", "PurchaseDetail"
        SUPPLIER = "Supplier", "Supplier"
        SPECIE = "Specie", "Specie"
        SPECIE_PARAMETER = "SpecieParameter", "SpecieParameter"
        SPECIE_FEEDING_REFERENCE = "SpecieFeedingReference", "SpecieFeedingReference"
        SPECIE_PRODUCTION_REFERENCE = (
            "SpecieProductionReference",
            "SpecieProductionReference",
        )
        BATCH = "Batch", "Batch"
        PRODUCTION_PLAN = "ProductionPlan", "ProductionPlan"
        CYCLE = "Cycle", "Cycle"
        FEEDING_SCHEDULE = "FeedingSchedule", "FeedingSchedule"
        FEEDING_PLAN = "FeedingPlan", "FeedingPlan"
        FEEDING_EVENT = "FeedingEvent", "FeedingEvent"
        DAILY_STAT = "DailyStat", "DailyStat"
        PRODUCT_USAGE_LOG = "ProductUsageLog", "ProductUsageLog"
        CONTROL_STAT = "ControlStat", "ControlStat"
        FISH_EVALUATED = "FishEvaluated", "FishEvaluated"
        HEALTH_STAT = "HealthStat", "HealthStat"
        TREATMENT_PLAN = "TreatmentPlan", "TreatmentPlan"
        TREATMENT_EVENT = "TreatmentEvent", "TreatmentEvent"
        AMBIENTAL_MEASUREMENT = "AmbientalMeasurement", "AmbientalMeasurement"
        ALERT = "Alert", "Alert"
        SALE = "Sale", "Sale"
        INVENTORY_MOVEMENT = "InventoryMovement", "InventoryMovement"
        HARVEST = "Harvest", "Harvest"
        HARVEST_CLASSIFICATION = "HarvestClassification", "HarvestClassification"
        CLIENT = "Client", "Client"
        BUY = "Buy", "Buy"
        INVITATION = "Invitation", "Invitation"
        BATCH_TRANSFER = "BatchTransfer", "BatchTransfer"
        GRADING_EVENT = "GradingEvent", "GradingEvent"
        SALE_DETAIL = "SaleDetail", "SaleDetail"
        CYCLE_POND_BATCH = "CyclePondBatch", "Cycle Pond Batch"
        POND_BATCH = "PondBatch", "PondBatch"
        SPECIE_POND_TYPE = "SpeciePondType", "SpeciePondType"
        PRODUCTION_REPORT = "ProductionReport", "Production Report"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    farm_id = models.IntegerField(null=True, blank=True)
    description = models.TextField()
    type_source = models.CharField(
        max_length=50,
        choices=TypeSource.choices,
    )
    source_id = models.IntegerField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["farm_id"]),
            models.Index(fields=["type_source"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"[{self.type_source}] {self.description} - {self.created_at}"


class Alert(models.Model):
    class SourceType(models.TextChoices):
        HEALTH = "Health", "Salud"
        HEALTH_STAT = "HealthStat", "Diagnóstico sanitario"
        STOCK = "Stock", "Stock"
        AMBIENTAL = "Ambiental", "Ambiental"
        CONTROL = "Control", "Control"
        FEEDING = "Feeding", "Alimentación"
        SALE = "Sale", "Venta"

    class Severity(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"
        CRITICAL = "critical", "Crítica"

    farm = models.ForeignKey(
        "farms.Farm", on_delete=models.CASCADE, related_name="alerts"
    )
    pond = models.ForeignKey(
        "ponds.Pond",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )
    cycle = models.ForeignKey(
        "cycle.Cycle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )

    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_id = models.PositiveIntegerField(null=True, blank=True)

    description = models.TextField()
    message = models.TextField()
    value = models.FloatField(null=True, blank=True)
    threshold = models.FloatField(null=True, blank=True)
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.MEDIUM
    )

    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_alerts",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "alert"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["farm", "is_resolved"]),
            models.Index(fields=["source_type", "source_id"]),
            models.Index(fields=["severity"]),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.source_type} - {self.farm} ({self.created_at:%Y-%m-%d})"
