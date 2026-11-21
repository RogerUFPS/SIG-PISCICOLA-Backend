from datetime import date

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.batch.models import PondBatch
from apps.batch.services.stock import transfer_pond_batch_quantity
from apps.cycle.models import Cycle, CyclePondBatch

from .models import GradingEvent


class GradingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradingEvent
        fields = [
            "id",
            "cycle",
            "source_pond_batch",
            "to_pond_batch",
            "quantity",
            "min_weight_g",
            "avg_weight_g",
            "max_weight_g",
            "date",
        ]
        read_only_fields = ["min_weight_g", "avg_weight_g", "max_weight_g"]

    def validate(self, data):
        cycle = data.get("cycle")
        source = data.get("source_pond_batch")
        destination = data.get("to_pond_batch")
        quantity = data.get("quantity")
        event_date = data.get("date")

        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError(
                {"quantity": "La cantidad debe ser mayor a 0."}
            )

        if event_date and event_date > date.today():
            raise serializers.ValidationError(
                {"date": "La fecha del evento no puede ser futura."}
            )

        if cycle and cycle.state != Cycle.State.IN_PROGRESS:
            raise serializers.ValidationError(
                {"cycle": "Solo se puede clasificar en ciclos que están en progreso."}
            )

        if (
            source
            and destination
            and source.batch.biological_state != destination.batch.biological_state
        ):
            raise serializers.ValidationError(
                {
                    "to_pond_batch": "Los lotes deben tener el mismo estado biológico para clasificar."
                }
            )

        # Validar que el origen está en el ciclo
        if cycle and source:
            if not CyclePondBatch.objects.filter(
                cycle=cycle, pond_batch=source
            ).exists():
                raise serializers.ValidationError(
                    {
                        "source_pond_batch": "El PondBatch origen no está actualmente en este ciclo."
                    }
                )

        # Validar que el DESTINO NO está en el ciclo (es decir, es un estanque SIN ciclo)
        if cycle and destination:
            if CyclePondBatch.objects.filter(
                cycle=cycle, pond_batch=destination
            ).exists():
                raise serializers.ValidationError(
                    {
                        "to_pond_batch": "El PondBatch destino no debe estar en este ciclo. "
                        "GradingEvent debe trasladar a un estanque SIN ciclo activo."
                    }
                )

        # Validar que el estanque destino NO tiene ciclo alguno (está sin ciclo)
        if destination:
            destination_pond = destination.pond
            # Verificar que no hay NINGÚN ciclo activo en el estanque destino
            active_cycle_in_dest_pond = CyclePondBatch.objects.filter(
                pond_batch__pond=destination_pond, cycle__state=Cycle.State.IN_PROGRESS
            ).exists()

            if active_cycle_in_dest_pond:
                raise serializers.ValidationError(
                    {
                        "to_pond_batch": "El estanque destino no puede tener un ciclo activo. "
                        "Solo se puede transferir a estanques sin ciclo."
                    }
                )

        if source and destination and source.pond == destination.pond:
            raise serializers.ValidationError(
                {
                    "to_pond_batch": "El estanque origen y destino no pueden ser el mismo."
                }
            )

        if source and quantity and source.current_quantity < quantity:
            raise serializers.ValidationError(
                {
                    "quantity": f"Cantidad insuficiente. Disponible: {source.current_quantity}."
                }
            )

        if destination and quantity:
            cantidad_actual_destino = (
                PondBatch.objects.filter(
                    pond=destination.pond, end_date__isnull=True
                ).aggregate(total=Sum("current_quantity"))["total"]
                or 0
            )

            if cantidad_actual_destino + quantity > destination.pond.capacity:
                raise serializers.ValidationError(
                    {
                        "to_pond_batch": f"El estanque destino '{destination.pond.name}' supera su capacidad de "
                        f"{destination.pond.capacity} peces. "
                        f"Disponible: {destination.pond.capacity - cantidad_actual_destino}."
                    }
                )

        if cycle and source and source.batch.specie != cycle.specie:
            raise serializers.ValidationError(
                {
                    "source_pond_batch": "La especie del lote no coincide con la especie del ciclo."
                }
            )

        if source and destination and source.batch.farm_id != destination.batch.farm_id:
            raise serializers.ValidationError(
                {"to_pond_batch": "Los lotes deben pertenecer a la misma granja."}
            )

        if cycle and destination and destination.batch.specie != cycle.specie:
            raise serializers.ValidationError(
                {
                    "to_pond_batch": "La especie del lote destino no coincide con la especie del ciclo."
                }
            )

        return data

    def create(self, validated_data):
        from apps.monitoring.services import BiomassCalculator

        source = validated_data["source_pond_batch"]
        destination = validated_data["to_pond_batch"]
        quantity = validated_data["quantity"]

        weights = BiomassCalculator.get_active_pond_weights(source.pond.id)
        validated_data["min_weight_g"] = weights["min_weight_g"]
        validated_data["avg_weight_g"] = weights["avg_weight_g"]
        validated_data["max_weight_g"] = weights["max_weight_g"]

        try:
            transfer_pond_batch_quantity(source, destination, quantity)
        except ValueError as e:
            raise serializers.ValidationError({"quantity": str(e)})

        return super().create(validated_data)

