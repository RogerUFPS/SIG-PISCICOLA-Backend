from django.db import models
from django.core.exceptions import ValidationError

from apps.batch.models import PondBatch


class ProductionPlan(models.Model):
    class Type(models.TextChoices):
        NURSERY = "nursery", "Nursery"
        GROWOUT = "growout", "Growout"
        BREEDING = "breeding", "Breeding"

    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE)
    specie = models.ForeignKey("species.Specie", on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=20, choices=Type.choices)
    total_days = models.PositiveIntegerField()
    expected_mortality_rate = models.FloatField()
    expected_final_weight = models.FloatField()
    expected_reproduction_rate = models.FloatField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "production_plan"
        ordering = ["-created_at"]
        verbose_name = "Production Plan"
        verbose_name_plural = "Production Plans"

    def __str__(self):
        return f"{self.name} v{self.version} - {self.specie}"


class Cycle(models.Model):
    class State(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        PAUSED = "paused", "Paused"
        FINISHED = "finished", "Finished"
        CANCELLED = "cancelled", "Cancelled"

    farm = models.ForeignKey("farms.Farm", on_delete=models.CASCADE)
    specie = models.ForeignKey("species.Specie", on_delete=models.CASCADE)
    production_plan = models.ForeignKey(ProductionPlan, on_delete=models.PROTECT)
    pond = models.ForeignKey("ponds.Pond", on_delete=models.PROTECT)  # Requerido - cada ciclo es para UN estanque específico
    name = models.CharField(max_length=150)
    start_date = models.DateField()
    estimated_finish_date = models.DateField()
    finish_date = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=20, choices=State.choices)
    comments = models.TextField(null=True, blank=True)
    min_weight_g = models.FloatField(null=True, blank=True)
    avg_weight_g = models.FloatField(null=True, blank=True)
    max_weight_g = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "cycle"
        ordering = ["-start_date"]
        verbose_name = "Cycle"
        verbose_name_plural = "Cycles"
        indexes = [
            models.Index(fields=["farm", "pond", "deleted_at"]),  # Queries rápidas por granja y estanque
            models.Index(fields=["pond", "state", "deleted_at"]),  # Obtener ciclos activos por estanque
        ]

    def __str__(self):
        return f"{self.name} - {self.state}"


class CyclePondBatch(models.Model):
    """Relación entre Ciclo y Lote en el estanque.
    
    Representa el lote usado en un ciclo específico. Permite actualizar
    parámetros de peso (min, avg, max) durante el ciclo.
    
    VALIDACIÓN: Todos los CyclePondBatch en un ciclo deben usar el MISMO estanque.
    """
    cycle = models.ForeignKey(Cycle, on_delete=models.CASCADE, related_name="cycle_pond_batches")
    pond_batch = models.ForeignKey(PondBatch, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    min_weight_g = models.FloatField()
    avg_weight_g = models.FloatField()
    max_weight_g = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cycle_batch"
        ordering = ["-created_at"]
        verbose_name = "Cycle Pond Batch"
        verbose_name_plural = "Cycle Pond Batches"
        indexes = [
            models.Index(fields=["cycle", "pond_batch"]),
        ]

    def clean(self):
        """Validar que el pond del pond_batch sea el MISMO que el del ciclo."""
        if self.pond_batch.pond_id != self.cycle.pond_id:
            raise ValidationError(
                f"El lote debe estar en el MISMO estanque del ciclo. "
                f"Ciclo en estanque {self.cycle.pond.code}, "
                f"pero lote en estanque {self.pond_batch.pond.code}."
            )

    def save(self, *args, **kwargs):
        self.full_clean()  # Ejecutar validaciones antes de guardar
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cycle.name} - Lote {self.pond_batch.batch.code} en {self.pond_batch.pond.code}"


__all__ = ["ProductionPlan", "Cycle", "CyclePondBatch"]
