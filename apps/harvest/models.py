# models.py

from django.conf import settings
from django.db import models


class Harvest(models.Model):
    class Type(models.TextChoices):
        TOTAL = "Total", "Total"
        PARTIAL = "Partial", "Parcial"

    class TraceabilityMode(models.TextChoices):
        PROPORTIONAL = "proportional", "Proportional"
        EXACT = "exact", "Exact"

    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="harvests",
    )
    cycle = models.ForeignKey(
        "cycle.Cycle",
        on_delete=models.PROTECT,
        related_name="harvests",
    )
    date = models.DateField()
    total_fish_count = models.PositiveIntegerField()
    total_weight_g = models.DecimalField(max_digits=14, decimal_places=2)
    min_weight_g = models.FloatField(default=0)
    avg_weight_g = models.FloatField(default=0)
    max_weight_g = models.FloatField(default=0)
    observations = models.TextField(blank=True)
    type = models.CharField(max_length=10, choices=Type.choices)
    traceability_mode = models.CharField(
        max_length=20,
        choices=TraceabilityMode.choices,
        default=TraceabilityMode.PROPORTIONAL,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="harvests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "harvest"
        ordering = ["-date"]

    def __str__(self):
        return f"Harvest [{self.type}] - {self.cycle} ({self.date})"


class HarvestSource(models.Model):
    class TraceabilityType(models.TextChoices):
        EXACT = "exact", "Exact"
        ESTIMATED = "estimated", "Estimated"
        PROPORTIONAL = "proportional", "Proportional"

    harvest = models.ForeignKey(
        Harvest,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    cycle_pond_batch = models.ForeignKey(
        "cycle.CyclePondBatch",
        on_delete=models.PROTECT,
        related_name="harvest_sources",
    )
    fish_count = models.PositiveIntegerField()
    total_weight_g = models.DecimalField(max_digits=14, decimal_places=2)
    traceability_type = models.CharField(
        max_length=20,
        choices=TraceabilityType.choices,
        default=TraceabilityType.PROPORTIONAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "harvest_source"
        constraints = [
            models.UniqueConstraint(
                fields=["harvest", "cycle_pond_batch"],
                name="uq_harvest_source_cycle_pond_batch",
            )
        ]

    def __str__(self):
        return (
            f"HarvestSource {self.harvest_id} <- "
            f"CyclePondBatch {self.cycle_pond_batch_id} ({self.fish_count})"
        )


class HarvestClassification(models.Model):
    class SizeCategory(models.TextChoices):
        SMALL = "Small", "Pequeño"
        MEDIUM = "Medium", "Mediano"
        LARGE = "Large", "Grande"
        EXTRA_LARGE = "Extra Large", "Extra Grande"

    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="harvest_classifications",
    )
    harvest = models.ForeignKey(
        Harvest,
        on_delete=models.PROTECT,
        related_name="classifications",
    )
    size_category = models.CharField(
        max_length=15,
        choices=SizeCategory.choices,
    )
    fish_count = models.PositiveIntegerField()
    total_weight_g = models.DecimalField(max_digits=14, decimal_places=2)
    reference_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    observations = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="harvest_classifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "harvest_classification"
        constraints = [
            models.UniqueConstraint(
                fields=["harvest", "size_category"],
                name="uq_harvest_size_category",
            )
        ]

    def __str__(self):
        return f"{self.size_category} - {self.harvest}"


class HarvestClassificationSource(models.Model):

    class TraceabilityType(models.TextChoices):
        EXACT = "exact", "Exact"
        PROPORTIONAL = "proportional", "Proportional"

    classification = models.ForeignKey(
        HarvestClassification,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    cycle_pond_batch = models.ForeignKey(
        "cycle.CyclePondBatch",
        on_delete=models.PROTECT,
        related_name="harvest_classification_sources",
    )
    fish_count = models.PositiveIntegerField()
    total_weight_g = models.DecimalField(max_digits=14, decimal_places=2)
    traceability_type = models.CharField(
        max_length=20,
        choices=TraceabilityType.choices,
        default=TraceabilityType.PROPORTIONAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "harvest_classification_source"
        constraints = [
            models.UniqueConstraint(
                fields=["classification", "cycle_pond_batch"],
                name="uq_harvest_classification_source_batch",
            )
        ]

    def __str__(self):
        return (
            f"ClassificationSource {self.classification_id} <- "
            f"CyclePondBatch {self.cycle_pond_batch_id} ({self.fish_count})"
        )


class HarvestClassificationDerivation(models.Model):

    classification = models.ForeignKey(
        HarvestClassification,
        on_delete=models.PROTECT,
        related_name="derivations",
    )
    batch = models.OneToOneField(
        "batch.Batch",
        on_delete=models.PROTECT,
        related_name="harvest_derivation",
    )
    fish_count = models.PositiveIntegerField()
    total_weight_g = models.DecimalField(max_digits=14, decimal_places=2)
    pond_id = models.PositiveIntegerField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="harvest_derivations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "harvest_classification_derivation"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Derivation {self.id} - classification {self.classification_id} "
            f"({self.fish_count} -> batch {self.batch_id})"
        )
