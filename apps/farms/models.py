# models.py
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models

User = get_user_model()


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "department"

    def __str__(self):
        return self.name


class City(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="cities"
    )

    class Meta:
        db_table = "city"
        unique_together = ("name", "department")

    def __str__(self):
        return f"{self.name}, {self.department.name}"


class Farm(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activa"
        INACTIVE = "inactive", "Inactiva"

    class WaterSource(models.TextChoices):
        RIVER = "river", "Río"
        STREAM = "stream", "Quebrada"
        LAKE = "lake", "Lago/Laguna"
        SPRING = "spring", "Manantial"
        RESERVOIR = "reservoir", "Embalse"
        DEEP_WELL = "deep_well", "Pozo profundo"
        MUNICIPAL = "municipal", "Acueducto municipal"
        IRRIGATION_CANAL = "irrigation_canal", "Canal de riego"
        RAINWATER = "rainwater", "Agua lluvia"

    name = models.CharField(max_length=255)
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="farms"
    )
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="farms")
    address = models.CharField(max_length=255)
    total_area_ha = models.DecimalField(max_digits=10, decimal_places=2)
    water_source = models.CharField(
        max_length=20,
        choices=WaterSource.choices,
        blank=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "farm"

    def __str__(self):
        return self.name


class FarmRole(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=100)
    permissions = models.PositiveSmallIntegerField(default=0)
    permissions_configured = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "farm_role"

    def __str__(self):
        return f"{self.farm} — {self.name}"


class FarmRoleAppPermission(models.Model):
    role = models.ForeignKey(
        FarmRole,
        on_delete=models.CASCADE,
        related_name="app_permissions",
    )
    app = models.CharField(max_length=50)
    can_view = models.BooleanField(default=False)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        db_table = "farm_role_app_permission"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "app"],
                name="unique_farm_role_app_permission",
            ),
        ]


class UserFarm(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Trabaja actualmente"
        INACTIVE = "inactive", "No trabaja actualmente"

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="user_farms"
    )
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="user_farms")
    farm_role = models.ForeignKey(
        FarmRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_farms",
    )
    permissions = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    is_owner = models.BooleanField(default=False)

    class Meta:
        db_table = "user_farm"
        constraints = [
            models.UniqueConstraint(fields=["user", "farm"], name="uq_user_farm")
        ]

    def clean(self):
        if self.farm_role and self.farm_role.farm_id != self.farm_id:
            raise ValidationError({"farm_role": "El rol no pertenece a esta finca."})

    def __str__(self):
        return f"{self.user} @ {self.farm}"
