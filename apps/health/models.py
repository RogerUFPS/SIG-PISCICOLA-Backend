from django.db import models


class HealthStat(models.Model):
    class SeverityLevel(models.TextChoices):
        LOW = "low", "Baja"
        MEDIUM = "medium", "Media"
        HIGH = "high", "Alta"
        CRITICAL = "critical", "Crítica"

    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="health_stats",
    )
    cycle = models.ForeignKey(
        "cycle.Cycle",
        on_delete=models.PROTECT,
        related_name="health_stats",
    )
    pond = models.ForeignKey(
        "ponds.Pond",
        on_delete=models.CASCADE,
        related_name="health_stats",
    )
    date = models.DateField()
    disease_name = models.CharField(max_length=255)
    severity_level = models.CharField(
        max_length=20,
        choices=SeverityLevel.choices,
    )
    comments = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="health_stats_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "health_stat"
        ordering = ["-date", "-created_at"]
        verbose_name = "Health Stat"
        verbose_name_plural = "Health Stats"
        indexes = [
            models.Index(fields=["farm", "cycle", "date"]),
            models.Index(fields=["pond", "date"]),
        ]

    def __str__(self):
        return f"{self.disease_name} ({self.severity_level}) — {self.date}"


class TreatmentPlan(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class ApplicationMethod(models.TextChoices):
        ORAL = "oral", "Oral (alimento medicado)"
        WATER_ADDITION = "water_addition", "Adición al agua del estanque"
        BATH = "bath", "Baño / inmersión corta"

    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="treatment_plans",
    )
    health_stat = models.ForeignKey(
        HealthStat,
        on_delete=models.PROTECT,
        related_name="treatment_plans",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="treatment_plans",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    dose_per_application = models.DecimalField(max_digits=10, decimal_places=4)
    unit = models.ForeignKey(
        "core.Unit",
        on_delete=models.PROTECT,
        related_name="treatment_plans",
    )
    times_per_day = models.PositiveIntegerField()
    gap_between_times_per_day = models.PositiveIntegerField(
        help_text="Minutos entre aplicaciones del mismo día.",
    )
    gap_between_completed_day = models.PositiveIntegerField(
        help_text="Días entre jornadas con aplicación (0 = todos los días).",
    )
    application_method = models.CharField(
        max_length=20,
        choices=ApplicationMethod.choices,
    )
    reason = models.TextField(null = True, blank=True)
    notes = models.TextField(null = True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="treatment_plans_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "treatment_plan"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["health_stat", "start_date", "end_date"]),
            models.Index(fields=["farm", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="treatment_plan_end_date_gte_start_date",
            ),
        ]

    def __str__(self):
        return (
            f"Plan {self.pk} — HealthStat {self.health_stat_id} — {self.health_stat.disease_name} "
            f"({self.start_date} → {self.end_date})"
        )


class TreatmentEvent(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"

    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="treatment_events",
    )
    cycle = models.ForeignKey(
        "cycle.Cycle",
        on_delete=models.PROTECT,
        related_name="treatment_events",
    )
    treatment_plan = models.ForeignKey(
        TreatmentPlan,
        on_delete=models.PROTECT,
        related_name="treatment_events",
    )
    date = models.DateField()
    scheduled_time = models.TimeField()
    application_number = models.PositiveIntegerField()
    planned_dose = models.DecimalField(max_digits=10, decimal_places=4)
    planned_unit = models.ForeignKey(
        "core.Unit",
        on_delete=models.PROTECT,
        related_name="treatment_events_planned",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    actual_dose = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
    )
    actual_unit = models.ForeignKey(
        "core.Unit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="treatment_events_actual",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="treatment_events_completed",
    )

    class Meta:
        db_table = "treatment_event"
        ordering = ["date", "scheduled_time", "application_number"]
        indexes = [
            models.Index(fields=["treatment_plan", "date"]),
            models.Index(fields=["cycle", "date", "status"]),
        ]

    def __str__(self):
        return (
            f"Aplicación {self.application_number} — "
            f"{self.date} {self.scheduled_time}"
        )
