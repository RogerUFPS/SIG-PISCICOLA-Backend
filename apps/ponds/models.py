# models.py

from django.db import models


class Pond(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"
        CLEANING = "cleaning", "En limpieza"
        IN_USE = "in_use", "En uso"

    class Type(models.TextChoices):
        DIRT = "dirt", "Tierra"
        CONCRETE = "concrete", "Concreto"
        GEOMEMBRANE = "geomembrane", "Geomembrana"
        FLOATING_CAGE = "floating_cage", "Jaula flotante"
        RACEWAY = "raceway", "Canal"
        ROUND_TANK = "round_tank", "Tanque redondo"

    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="ponds",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, editable=False)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    capacity = models.DecimalField(max_digits=10, decimal_places=2)
    area = models.DecimalField(max_digits=10, decimal_places=2)
    volume = models.DecimalField(max_digits=10, decimal_places=2)
    depth = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pond"
        constraints = [
            models.UniqueConstraint(fields=["name", "farm"], name="uq_pond_name_farm"),
            models.UniqueConstraint(fields=["code", "farm"], name="uq_pond_code_farm"),
        ]

    def __str__(self):
        return f"{self.name} ({self.farm})"

    def save(self, *args, **kwargs):
        if not self.code:
            from .utils import generate_pond_code

            code = generate_pond_code()
            while Pond.objects.filter(code=code, farm=self.farm).exists():
                code = generate_pond_code()
            self.code = code
        super().save(*args, **kwargs)


class UserFarmPond(models.Model):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="user_farm_ponds",
    )
    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.CASCADE,
        related_name="user_farm_ponds",
    )
    pond = models.ForeignKey(
        Pond,
        on_delete=models.CASCADE,
        related_name="user_farm_ponds",
    )

    class Meta:
        db_table = "user_farm_pond"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "farm", "pond"],
                name="uq_user_farm_pond",
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.pond}"
