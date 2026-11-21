from django.db import models


class Batch(models.Model):
    class OriginType(models.TextChoices):
        HARVEST_CLASSIFICATION = "harvest_classification", "Harvest Classification"
        PURCHASE_DETAIL = "purchase_detail", "Purchase Detail"
        BATCH_SPLIT = "batch_split", "Batch Split"
        INITIAL = "initial", "Initial"

    class BiologicalState(models.TextChoices):
        ALEVIN = "alevin", "Alevin"
        RISING = "rising", "Rising"
        FATTING = "fatting", "Fatting"
        BREEDING = "breeding", "Breeding"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONSUMED = "consumed", "Consumed"
        FINISHED = "finished", "Finished"
        DEAD = "dead", "Dead"

    specie = models.ForeignKey("species.Specie", on_delete=models.CASCADE)
    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE)
    origin_type = models.CharField(
        max_length=50, choices=OriginType.choices, default=OriginType.INITIAL
    )
    origin_id = models.PositiveIntegerField(null=True, blank=True)
    code = models.CharField(max_length=50)
    biological_state = models.CharField(
        max_length=20, choices=BiologicalState.choices, default=BiologicalState.ALEVIN
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    comments = models.TextField(null=True, blank=True)
    initial_quantity = models.PositiveIntegerField()
    min_weight_g = models.FloatField()
    avg_weight_g = models.FloatField()
    max_weight_g = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "batch"
        ordering = ["-created_at"]
        unique_together = ("code", "farm")
        verbose_name = "Batch"
        verbose_name_plural = "Batches"

    def __str__(self):
        return f"Batch {self.code} - {self.specie}"


class BatchSource(models.Model):
    parent_batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name="children"
    )
    child_batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, related_name="parents"
    )
    quantity = models.PositiveIntegerField()

    class Meta:
        db_table = "batch_source"
        unique_together = ("parent_batch", "child_batch")
        verbose_name = "Batch Source"
        verbose_name_plural = "Batch Sources"

    def __str__(self):
        return f"{self.parent_batch.code} -> {self.child_batch.code} ({self.quantity})"


class PondBatch(models.Model):
    pond = models.ForeignKey("ponds.Pond", on_delete=models.CASCADE)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE)
    initial_quantity = models.PositiveIntegerField()
    current_quantity = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "pond_batch"
        ordering = ["-start_date"]
        verbose_name = "Pond Batch"
        verbose_name_plural = "Pond Batches"

    def __str__(self):
        return f"{self.batch.code} in {self.pond.code} ({self.current_quantity} units)"


class BatchTransfer(models.Model):
    source_pond_batch = models.ForeignKey(
        PondBatch, on_delete=models.CASCADE, related_name="transfers_out"
    )
    to_pond_batch = models.ForeignKey(
        PondBatch, on_delete=models.CASCADE, related_name="transfers_in"
    )
    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    date = models.DateField()
    reason = models.TextField()

    class Meta:
        db_table = "batch_transfer"
        ordering = ["-date"]
        verbose_name = "Batch Transfer"
        verbose_name_plural = "Batch Transfers"

    def __str__(self):
        return f"Transfer {self.quantity} units from {self.source_pond_batch.pond.code} to {self.to_pond_batch.pond.code} on {self.date}"


__all__ = ["Batch", "BatchSource", "PondBatch", "BatchTransfer"]
