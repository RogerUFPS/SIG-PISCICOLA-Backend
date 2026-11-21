from django.db import models


class FeedingSchedule(models.Model):
    class Stage(models.TextChoices):
        ALEVIN = "alevin", "Alevín"
        RISING = "rising", "Levante"
        FATTING = "fatting", "Engorde"
        BREEDING = "breeding", "Reproducción"

    class FeedForm(models.TextChoices):
        PELLET = "pellet", "Pellet"
        EXTRUDED = "extruded", "Extruido"
        CRUMBLE = "crumble", "Migaja"
        POWDER = "powder", "Polvo"

    farm = models.ForeignKey(
        "farms.Farm", on_delete=models.CASCADE, related_name="feeding_schedules"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.PROTECT, related_name="feeding_schedules"
    )
    specie = models.ForeignKey(
        "species.Specie", on_delete=models.PROTECT, related_name="feeding_schedules"
    )
    name = models.CharField(max_length=100)
    comments = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=Stage.choices)
    aceptable_min_weight_g = models.DecimalField(max_digits=10, decimal_places=2)
    aceptable_max_weight_g = models.DecimalField(max_digits=10, decimal_places=2)
    feed_form = models.CharField(max_length=20, choices=FeedForm.choices)
    pellet_size_mm = models.DecimalField(max_digits=5, decimal_places=2)
    feeding_rate_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    times_per_day = models.PositiveIntegerField()
    gap_between_times_per_day = models.PositiveIntegerField(
        help_text="Minutos entre raciones del mismo día"
    )
    gap_between_completed_day = models.PositiveIntegerField(
        help_text="Días entre jornadas de alimentación (0 = todos los días; 1 = día sí día no; etc.)."
    )
    expected_fca = models.DecimalField(max_digits=5, decimal_places=2)
    expected_daily_gain_g = models.DecimalField(max_digits=8, decimal_places=2)
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "feeding_schedule"

    def __str__(self):
        return f"{self.name} v{self.version} — {self.farm}"


class FeedingPlan(models.Model):
    farm = models.ForeignKey(
        "farms.Farm", on_delete=models.CASCADE, related_name="feeding_plans"
    )
    cycle = models.ForeignKey(
        "cycle.Cycle", on_delete=models.PROTECT, related_name="feeding_plans"
    )
    feeding_schedule = models.ForeignKey(
        FeedingSchedule,
        on_delete=models.PROTECT,
        related_name="feeding_plans",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "feeding_plan"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Plan ciclo {self.cycle_id} — {self.start_date} → {self.end_date}"


class FeedingEvent(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"

    farm = models.ForeignKey(
        "farms.Farm", on_delete=models.CASCADE, related_name="feeding_events"
    )
    cycle = models.ForeignKey(
        "cycle.Cycle", on_delete=models.PROTECT, related_name="feeding_events"
    )
    feeding_plan = models.ForeignKey(
        FeedingPlan,
        on_delete=models.PROTECT,
        related_name="feeding_events",
    )
    date = models.DateField()
    scheduled_time = models.TimeField()
    ration_number = models.PositiveIntegerField()
    planned_quantity = models.DecimalField(max_digits=14, decimal_places=6)
    planned_unit = models.ForeignKey(
        "core.Unit",
        on_delete=models.PROTECT,
        related_name="feeding_events_planned",
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    completed_at = models.DateTimeField(null=True, blank=True)
    actual_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    actual_unit = models.ForeignKey(
        "core.Unit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="feeding_events_actual",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feeding_events_completed",
    )

    class Meta:
        db_table = "feeding_event"
        ordering = ["date", "scheduled_time", "ration_number"]

    def __str__(self):
        return f"Evento {self.ration_number} — {self.date} {self.scheduled_time}"
