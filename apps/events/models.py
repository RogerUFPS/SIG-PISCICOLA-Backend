from django.db import models

from apps.batch.models import PondBatch
from apps.cycle.models import Cycle


class GradingEvent(models.Model):
    cycle = models.ForeignKey(Cycle, on_delete=models.CASCADE)
    source_pond_batch = models.ForeignKey(
        PondBatch, on_delete=models.CASCADE, related_name="grading_out"
    )
    to_pond_batch = models.ForeignKey(
        PondBatch, on_delete=models.CASCADE, related_name="grading_in"
    )
    quantity = models.PositiveIntegerField()
    min_weight_g = models.FloatField()
    avg_weight_g = models.FloatField()
    max_weight_g = models.FloatField()
    date = models.DateField()

    class Meta:
        db_table = "grading_event"
        ordering = ["-date"]
        verbose_name = "Grading Event"
        verbose_name_plural = "Grading Events"

    def __str__(self):
        return f"Grading {self.quantity} units on {self.date}"


__all__ = ["GradingEvent"]
