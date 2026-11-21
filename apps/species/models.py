from django.db import models


class Specie(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    feeding_rate = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        db_table = "specie"
        verbose_name = "Specie"
        verbose_name_plural = "Species"

    def __str__(self):
        return self.name


class SpeciePondType(models.Model):
    class PondType(models.TextChoices):
        DIRT = "dirt", "Tierra"
        CONCRETE = "concrete", "Concreto"
        GEOMEMBRANE = "geomembrane", "Geomembrana"
        FLOATING_CAGE = "floating_cage", "Jaula flotante"
        RACEWAY = "raceway", "Canal"
        ROUND_TANK = "round_tank", "Tanque redondo"

    specie = models.ForeignKey( Specie, on_delete=models.CASCADE, related_name="pond_types")
    pond_type = models.CharField(max_length=20, choices=PondType.choices)

    class Meta:
        db_table = "specie_pond_type"
        constraints = [
            models.UniqueConstraint(
                fields=["specie", "pond_type"],
                name="uq_specie_pond_type",
            )
        ]

    def __str__(self):
        return f"{self.specie} — {self.pond_type}"


class SpecieParameter(models.Model):
    class ParameterType(models.TextChoices):
        TEMPERATURE = "temperature", "Temperatura"
        DISSOLVED_OXYGEN = "dissolved_oxygen", "Oxígeno disuelto"
        PH = "ph", "pH"
        TURBIDITY = "turbidity", "Turbidez"
        ALKALINITY = "alkalinity", "Alcalinidad"
        CONDUCTIVITY = "conductivity", "Conductividad"

    specie = models.ForeignKey(
        Specie,
        on_delete=models.CASCADE,
        related_name="parameters",
    )
    parameter_type = models.CharField(max_length=20, choices=ParameterType.choices)
    unit = models.ForeignKey(
        "core.Unit",
        on_delete=models.PROTECT,
        related_name="specie_parameters",
    )
    min_value = models.DecimalField(max_digits=10, decimal_places=4)
    max_value = models.DecimalField(max_digits=10, decimal_places=4)
    alert_threshold = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        db_table = "specie_parameter"
        constraints = [
            models.UniqueConstraint(
                fields=["specie", "parameter_type"],
                name="uq_specie_parameter_type",
            )
        ]

    def __str__(self):
        return f"{self.specie} — {self.parameter_type}"


class SpecieFeedingReference(models.Model):
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

    specie = models.ForeignKey(
        Specie,
        on_delete=models.CASCADE,
        related_name="feeding_references",
    )
    stage = models.CharField(max_length=20, choices=Stage.choices)
    min_weight_g = models.DecimalField(max_digits=10, decimal_places=2)
    max_weight_g = models.DecimalField(max_digits=10, decimal_places=2)
    recommended_protein_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    recommended_pellet_size_mm = models.DecimalField(max_digits=5, decimal_places=2)
    recommended_feed_form = models.CharField(max_length=20, choices=FeedForm.choices)
    recommended_feeding_rate_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    reference_fca_min = models.DecimalField(max_digits=5, decimal_places=2)
    reference_fca_max = models.DecimalField(max_digits=5, decimal_places=2)
    reference_daily_gain_g_min = models.DecimalField(max_digits=8, decimal_places=2)
    reference_daily_gain_g_max = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        db_table = "specie_feeding_reference"
        constraints = [
            models.UniqueConstraint(
                fields=["specie", "stage", "recommended_feed_form"],
                name="uq_specie_feeding_reference_stage_feed_form",
            )
        ]

    def __str__(self):
        return f"{self.specie} — {self.stage} — {self.recommended_feed_form}"


class SpecieProductionReference(models.Model):
    class Type(models.TextChoices):
        NURSERY = "nursery", "Alevinaje"
        GROWOUT = "growout", "Engorde"
        BREEDING = "breeding", "Reproducción"

    specie = models.ForeignKey(
        Specie,
        on_delete=models.CASCADE,
        related_name="production_references",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    reference_total_days_min = models.PositiveIntegerField()
    reference_total_days_max = models.PositiveIntegerField()
    reference_mortality_rate_min = models.DecimalField(max_digits=5, decimal_places=4)
    reference_mortality_rate_max = models.DecimalField(max_digits=5, decimal_places=4)
    reference_final_weight_min_g = models.DecimalField(max_digits=10, decimal_places=2)
    reference_final_weight_max_g = models.DecimalField(max_digits=10, decimal_places=2)
    reference_reproduction_rate_min = models.DecimalField(max_digits=5, decimal_places=4)
    reference_reproduction_rate_max = models.DecimalField(max_digits=5, decimal_places=4)

    class Meta:
        db_table = "specie_production_reference"
        constraints = [
            models.UniqueConstraint(
                fields=["specie", "type"],
                name="uq_specie_production_reference_type",
            )
        ]

    def __str__(self):
        return f"{self.specie} — {self.type}"
