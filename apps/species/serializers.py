from rest_framework import serializers

from .models import (
    Specie,
    SpecieFeedingReference,
    SpecieParameter,
    SpeciePondType,
    SpecieProductionReference,
)


class SpecieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specie
        fields = ["id", "name", "description", "feeding_rate"]

    def validate_name(self, value):
        qs = Specie.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe una especie con este nombre."
            )
        return value


class SpeciePondTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpeciePondType
        fields = ["id", "specie", "pond_type"]
        read_only_fields = ["specie"]

    def validate(self, data):
        specie = self.context["specie"]
        pond_type = data.get("pond_type")

        qs = SpeciePondType.objects.filter(specie=specie, pond_type=pond_type)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"pond_type": "Este tipo de estanque ya está registrado para esta especie."}
            )
        return data


class SpecieParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecieParameter
        fields = [
            "id",
            "specie",
            "parameter_type",
            "unit",
            "min_value",
            "max_value",
            "alert_threshold",
        ]
        read_only_fields = ["specie"]

    def validate_min_value(self, value):
        if value < 0:
            raise serializers.ValidationError("El valor mínimo no puede ser negativo.")
        return value

    def validate_max_value(self, value):
        if value < 0:
            raise serializers.ValidationError("El valor máximo no puede ser negativo.")
        return value

    def validate_alert_threshold(self, value):
        if value <= 0:
            raise serializers.ValidationError("El umbral de alerta debe ser mayor a 0.")
        return value

    def validate(self, data):
        min_value = data.get("min_value", getattr(self.instance, "min_value", None))
        max_value = data.get("max_value", getattr(self.instance, "max_value", None))
        alert_threshold = data.get("alert_threshold", getattr(self.instance, "alert_threshold", None))
        parameter_type = data.get("parameter_type", getattr(self.instance, "parameter_type", None))
        specie = self.context.get("specie")

        if specie and parameter_type:
            qs = SpecieParameter.objects.filter(specie=specie, parameter_type=parameter_type)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"parameter_type": "Esta especie ya tiene registrado este tipo de parámetro."}
                )

        if min_value is not None and max_value is not None:
            if min_value >= max_value:
                raise serializers.ValidationError(
                    {"min_value": "El valor mínimo debe ser menor que el máximo."}
                )
            if alert_threshold is not None:
                half_range = (max_value - min_value) / 2
                if alert_threshold >= half_range:
                    raise serializers.ValidationError(
                        {
                            "alert_threshold": (
                                f"El umbral de alerta ({alert_threshold}) debe ser menor que la "
                                f"mitad del rango ({half_range}), de lo contrario no existe zona segura."
                            )
                        }
                    )

        return data


class SpecieFeedingReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecieFeedingReference
        fields = [
            "id",
            "specie",
            "stage",
            "min_weight_g",
            "max_weight_g",
            "recommended_protein_percentage",
            "recommended_pellet_size_mm",
            "recommended_feed_form",
            "recommended_feeding_rate_percentage",
            "reference_fca_min",
            "reference_fca_max",
            "reference_daily_gain_g_min",
            "reference_daily_gain_g_max",
        ]
        read_only_fields = ["specie"]

    def validate_min_weight_g(self, value):
        if value <= 0:
            raise serializers.ValidationError("El peso mínimo debe ser mayor a 0.")
        return value

    def validate_max_weight_g(self, value):
        if value <= 0:
            raise serializers.ValidationError("El peso máximo debe ser mayor a 0.")
        return value

    def validate_recommended_protein_percentage(self, value):
        if not (0 < value <= 100):
            raise serializers.ValidationError("El porcentaje de proteína debe ser mayor a 0 y máximo 100.")
        return value

    def validate_recommended_pellet_size_mm(self, value):
        if value <= 0:
            raise serializers.ValidationError("El tamaño del pellet debe ser mayor a 0.")
        return value

    def validate_recommended_feeding_rate_percentage(self, value):
        if not (0 < value <= 100):
            raise serializers.ValidationError("El porcentaje de alimentación debe ser mayor a 0 y máximo 100.")
        return value

    def validate_reference_fca_min(self, value):
        if value <= 0:
            raise serializers.ValidationError("El FCA mínimo debe ser mayor a 0.")
        return value

    def validate_reference_fca_max(self, value):
        if value <= 0:
            raise serializers.ValidationError("El FCA máximo debe ser mayor a 0.")
        return value

    def validate_reference_daily_gain_g_min(self, value):
        if value <= 0:
            raise serializers.ValidationError("La ganancia diaria mínima debe ser mayor a 0.")
        return value

    def validate_reference_daily_gain_g_max(self, value):
        if value <= 0:
            raise serializers.ValidationError("La ganancia diaria máxima debe ser mayor a 0.")
        return value

    def validate(self, data):
        min_w = data.get("min_weight_g", getattr(self.instance, "min_weight_g", None))
        max_w = data.get("max_weight_g", getattr(self.instance, "max_weight_g", None))
        fca_min = data.get("reference_fca_min", getattr(self.instance, "reference_fca_min", None))
        fca_max = data.get("reference_fca_max", getattr(self.instance, "reference_fca_max", None))
        gain_min = data.get("reference_daily_gain_g_min", getattr(self.instance, "reference_daily_gain_g_min", None))
        gain_max = data.get("reference_daily_gain_g_max", getattr(self.instance, "reference_daily_gain_g_max", None))
        stage = data.get("stage", getattr(self.instance, "stage", None))
        feed_form = data.get(
            "recommended_feed_form",
            getattr(self.instance, "recommended_feed_form", None),
        )
        specie = self.context.get("specie")

        if specie and stage and feed_form:
            qs = SpecieFeedingReference.objects.filter(
                specie=specie,
                stage=stage,
                recommended_feed_form=feed_form,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {
                        "recommended_feed_form": (
                            "Esta especie ya tiene una referencia de alimentación "
                            "para esta etapa y esta forma de alimento."
                        )
                    }
                )

        if min_w is not None and max_w is not None and min_w > max_w:
            raise serializers.ValidationError(
                {"min_weight_g": "El peso mínimo no puede ser mayor que el máximo."}
            )
        if fca_min is not None and fca_max is not None and fca_min > fca_max:
            raise serializers.ValidationError(
                {"reference_fca_min": "El FCA mínimo no puede ser mayor que el máximo."}
            )
        if gain_min is not None and gain_max is not None and gain_min > gain_max:
            raise serializers.ValidationError(
                {"reference_daily_gain_g_min": "La ganancia diaria mínima no puede ser mayor que la máxima."}
            )

        return data


class SpecieProductionReferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecieProductionReference
        fields = [
            "id",
            "specie",
            "type",
            "reference_total_days_min",
            "reference_total_days_max",
            "reference_mortality_rate_min",
            "reference_mortality_rate_max",
            "reference_final_weight_min_g",
            "reference_final_weight_max_g",
            "reference_reproduction_rate_min",
            "reference_reproduction_rate_max",
        ]
        read_only_fields = ["specie"]

    def validate_reference_mortality_rate_min(self, value):
        if not (0 <= value <= 1):
            raise serializers.ValidationError("La tasa de mortalidad mínima debe estar entre 0 y 1.")
        return value

    def validate_reference_mortality_rate_max(self, value):
        if not (0 <= value <= 1):
            raise serializers.ValidationError("La tasa de mortalidad máxima debe estar entre 0 y 1.")
        return value

    def validate_reference_final_weight_min_g(self, value):
        if value <= 0:
            raise serializers.ValidationError("El peso final mínimo debe ser mayor a 0.")
        return value

    def validate_reference_final_weight_max_g(self, value):
        if value <= 0:
            raise serializers.ValidationError("El peso final máximo debe ser mayor a 0.")
        return value

    def validate_reference_reproduction_rate_min(self, value):
        if value < 0:
            raise serializers.ValidationError("La tasa de reproducción mínima no puede ser negativa.")
        return value

    def validate_reference_reproduction_rate_max(self, value):
        if value < 0:
            raise serializers.ValidationError("La tasa de reproducción máxima no puede ser negativa.")
        return value

    def validate(self, data):
        days_min = data.get("reference_total_days_min", getattr(self.instance, "reference_total_days_min", None))
        days_max = data.get("reference_total_days_max", getattr(self.instance, "reference_total_days_max", None))
        mort_min = data.get("reference_mortality_rate_min", getattr(self.instance, "reference_mortality_rate_min", None))
        mort_max = data.get("reference_mortality_rate_max", getattr(self.instance, "reference_mortality_rate_max", None))
        weight_min = data.get("reference_final_weight_min_g", getattr(self.instance, "reference_final_weight_min_g", None))
        weight_max = data.get("reference_final_weight_max_g", getattr(self.instance, "reference_final_weight_max_g", None))
        production_type = data.get("type", getattr(self.instance, "type", None))
        specie = self.context.get("specie")

        if specie and production_type:
            qs = SpecieProductionReference.objects.filter(specie=specie, type=production_type)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"type": "Esta especie ya tiene una referencia de producción para este tipo."}
                )
        repro_min = data.get("reference_reproduction_rate_min", getattr(self.instance, "reference_reproduction_rate_min", None))
        repro_max = data.get("reference_reproduction_rate_max", getattr(self.instance, "reference_reproduction_rate_max", None))

        if days_min is not None and days_max is not None and days_min > days_max:
            raise serializers.ValidationError(
                {"reference_total_days_min": "Los días mínimos no pueden ser mayores que los máximos."}
            )

        if mort_min is not None and mort_max is not None and mort_min > mort_max:
            raise serializers.ValidationError(
                {"reference_mortality_rate_min": "La tasa de mortalidad mínima no puede ser mayor que la máxima."}
            )
        if weight_min is not None and weight_max is not None and weight_min > weight_max:
            raise serializers.ValidationError(
                {"reference_final_weight_min_g": "El peso final mínimo no puede ser mayor que el máximo."}
            )
        if repro_min is not None and repro_max is not None and repro_min > repro_max:
            raise serializers.ValidationError(
                {"reference_reproduction_rate_min": "La tasa de reproducción mínima no puede ser mayor que la máxima."}
            )

        return data
