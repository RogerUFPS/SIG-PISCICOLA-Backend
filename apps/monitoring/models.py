from django.db import models
from django.utils import timezone
from django.conf import settings


class FishEvaluated(models.Model):
    """
    Representa la evaluación individual de peces en un momento determinado.
    """
    class Type(models.TextChoices):
        CONTROL_STAT = "control_stat", "Control Stat"
        HEALTH_STAT = "health_stat", "Health Stat"

    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="fish_evaluations",
        null=True,
        blank=True,
    )
    cycle = models.ForeignKey(
        "cycle.Cycle",
        on_delete=models.CASCADE,
        related_name="fish_evaluations",
    )
    pond = models.ForeignKey(
        "ponds.Pond",
        on_delete=models.CASCADE,
        related_name="fish_evaluations",
    )
    evaluation_date = models.DateField()
    sampled_quantity = models.PositiveIntegerField()
    min_weight_g = models.FloatField()
    avg_weight_g = models.FloatField()
    max_weight_g = models.FloatField()
    mortality_quantity = models.PositiveIntegerField(default=0)
    observations = models.TextField(null=True, blank=True)
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.HEALTH_STAT,
    )
    source_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID de ControlStat si type=control_stat, ID de evento de salud si type=health_stat",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fish_evaluations_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "fish_evaluated"
        ordering = ["-evaluation_date"]
        verbose_name = "Fish Evaluation"
        verbose_name_plural = "Fish Evaluations"

    def __str__(self):
        return f"Evaluation {self.id} - Cycle {self.cycle.name} - {self.evaluation_date}"


class DailyStat(models.Model):
    """
    Estadística diaria flexible, puede contener cualquier registro del día.
    """
    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="daily_stats",
        null=True,
        blank=True,
    )
    cycle = models.ForeignKey(
        "cycle.Cycle",
        on_delete=models.CASCADE,
        related_name="daily_stats",
    )
    pond = models.ForeignKey(
        "ponds.Pond",
        on_delete=models.CASCADE,
        related_name="daily_stats",
    )
    stat_date = models.DateField()
    name = models.CharField(max_length=150)
    description = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="daily_stats_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "daily_stat"
        ordering = ["-stat_date", "-created_at"]
        verbose_name = "Daily Stat"
        verbose_name_plural = "Daily Stats"

    def __str__(self):
        return f"Daily Stat {self.id} - {self.stat_date}: {self.name}"


class ProductUsageLog(models.Model):
    """
    Registro de uso de productos (alimento u otros).
    """
    daily_stat = models.ForeignKey(
        DailyStat,
        on_delete=models.CASCADE,
        related_name="product_usages",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
    )
    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="product_usage_logs",
        null=True,
        blank=True,
    )
    quantity_used = models.FloatField()
    unit = models.ForeignKey(
        "core.Unit",
        on_delete=models.PROTECT,
        related_name="product_usages",
    )
    batch = models.ForeignKey(
        "batch.Batch",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_usage_log"
        ordering = ["-created_at"]
        verbose_name = "Product Usage Log"
        verbose_name_plural = "Product Usage Logs"

    def __str__(self):
        return f"Usage {self.id} - {self.product.name} x{self.quantity_used}{self.unit}"


class ControlStat(models.Model):
    """
    Estadística de control cada ~15 días. Datos calculados automáticamente a partir de FishEvaluated.
    """
    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="control_stats",
        null=True,
        blank=True,
    )
    cycle = models.ForeignKey(
        "cycle.Cycle",
        on_delete=models.CASCADE,
        related_name="control_stats",
    )
    pond = models.ForeignKey(
        "ponds.Pond",
        on_delete=models.CASCADE,
        related_name="control_stats",
    )
    control_date = models.DateField()
    sampled_quantity = models.PositiveIntegerField()
    live_quantity = models.PositiveIntegerField()
    min_weight_g = models.FloatField()
    avg_weight_g = models.FloatField()
    max_weight_g = models.FloatField()
    mortality_percentage = models.FloatField()
    biomass_kg = models.FloatField()
    fca = models.FloatField(null=True, blank=True)
    biomass_gain_kg = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="control_stats_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "control_stat"
        ordering = ["-control_date"]
        unique_together = ("cycle", "pond", "control_date")
        verbose_name = "Control Stat"
        verbose_name_plural = "Control Stats"

    def __str__(self):
        return f"Control {self.id} - Cycle {self.cycle.name} - {self.control_date}"


__all__ = [
    "FishEvaluated",
    "DailyStat",
    "ProductUsageLog",
    "ControlStat",
]
