from rest_framework import serializers

from apps.cycle.models import Cycle

from .constants import ALL_MODULES, EXPORT_FORMATS


class ProductionReportRequestSerializer(serializers.Serializer):
    modules = serializers.ListField(
        child=serializers.ChoiceField(choices=ALL_MODULES),
        min_length=1,
        help_text="Módulos a incluir: feeding, biometry, health, harvest, sales",
    )
    format = serializers.ChoiceField(
        choices=EXPORT_FORMATS,
        help_text="Formato de exportación: pdf o xlsx",
    )
    cycle_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Ciclo consultado en trazabilidad (opcional; filtra el alcance del reporte)",
    )

    def validate_modules(self, value):
        unique = list(dict.fromkeys(value))
        return unique

    def validate(self, attrs):
        cycle_id = attrs.get("cycle_id")
        farm_id = self.context.get("farm_id")
        batch_id = self.context.get("batch_id")
        if cycle_id is None or not farm_id or not batch_id:
            return attrs

        if not Cycle.objects.filter(id=cycle_id, farm_id=farm_id).exists():
            raise serializers.ValidationError(
                {"cycle_id": "El ciclo no pertenece a esta granja."}
            )

        from apps.cycle.models import CyclePondBatch

        if not CyclePondBatch.objects.filter(
            cycle_id=cycle_id,
            pond_batch__batch_id=batch_id,
        ).exists():
            raise serializers.ValidationError(
                {
                    "cycle_id": (
                        "El ciclo no está asociado al lote seleccionado "
                        "en trazabilidad."
                    )
                }
            )
        return attrs
