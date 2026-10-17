from datetime import date

from rest_framework import serializers

from apps.batch.models import Batch, PondBatch
from apps.cycle.services.lifecycle import cancel_cycle, finish_cycle
from apps.ponds.models import Pond
from apps.species.models import Specie

from .models import Cycle, CyclePondBatch, ProductionPlan

# Nested serializers para visualización detallada


class SpecieMinimalSerializer(serializers.ModelSerializer):
    """Serializer mínimo de Especie para usar en contextos anidados"""

    class Meta:
        model = Specie
        fields = ["id", "name"]


class BatchDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de Batch con información de la especie"""

    specie = SpecieMinimalSerializer(read_only=True)

    class Meta:
        model = Batch
        fields = [
            "id",
            "code",
            "specie",
            "biological_state",
            "status",
            "origin_type",
            "initial_quantity",
            "min_weight_g",
            "avg_weight_g",
            "max_weight_g",
            "comments",
        ]


class PondDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de Estanque"""

    class Meta:
        model = Pond
        fields = [
            "id",
            "code",
            "name",
            "status",
            "type",
            "capacity",
            "area",
            "volume",
            "depth",
        ]


class PondBatchDetailSerializer(serializers.ModelSerializer):
    """Serializer detallado de PondBatch con batch y estanque anidados"""

    batch = BatchDetailSerializer(read_only=True)
    pond = PondDetailSerializer(read_only=True)

    class Meta:
        model = PondBatch
        fields = [
            "id",
            "batch",
            "pond",
            "initial_quantity",
            "current_quantity",
            "start_date",
            "end_date",
        ]


class ProductionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductionPlan
        fields = [
            "id",
            "farm",
            "specie",
            "name",
            "type",
            "total_days",
            "expected_mortality_rate",
            "expected_final_weight",
            "expected_reproduction_rate",
            "version",
            "is_current",
            "parent",
            "created_at",
            "updated_at",
            "deleted_at",
        ]
        read_only_fields = [
            "farm",
            "version",
            "is_current",
            "parent",
            "created_at",
            "updated_at",
            "deleted_at",
        ]

    def validate(self, data):
        if self.instance is not None and "specie" in data:
            raise serializers.ValidationError(
                {
                    "specie": "La especie no se puede cambiar al versionar un plan de producción."
                }
            )

        expected_mortality_rate = data.get("expected_mortality_rate")
        expected_final_weight = data.get("expected_final_weight")

        if expected_mortality_rate is not None:
            if not (0 <= expected_mortality_rate <= 100):
                raise serializers.ValidationError(
                    {
                        "expected_mortality_rate": "El porcentaje de mortalidad debe estar entre 0 y 100."
                    }
                )

        if expected_final_weight is not None and expected_final_weight <= 0:
            raise serializers.ValidationError(
                {"expected_final_weight": "El peso final esperado debe ser mayor a 0."}
            )

        return data

    def update(self, instance, validated_data):
        if not instance.is_current:
            raise serializers.ValidationError(
                "No se puede actualizar un plan que no es la versión actual."
            )

        new_plan = ProductionPlan.objects.create(
            farm=instance.farm,
            specie=instance.specie,
            name=validated_data.get("name", instance.name),
            type=validated_data.get("type", instance.type),
            total_days=validated_data.get("total_days", instance.total_days),
            expected_mortality_rate=validated_data.get(
                "expected_mortality_rate", instance.expected_mortality_rate
            ),
            expected_final_weight=validated_data.get(
                "expected_final_weight", instance.expected_final_weight
            ),
            expected_reproduction_rate=validated_data.get(
                "expected_reproduction_rate", instance.expected_reproduction_rate
            ),
            version=instance.version + 1,
            is_current=True,
            parent=instance,
        )

        instance.is_current = False
        instance.save(update_fields=["is_current"])

        return new_plan


class CycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cycle
        fields = [
            "id",
            "farm",
            "specie",
            "production_plan",
            "pond",
            "name",
            "start_date",
            "estimated_finish_date",
            "finish_date",
            "state",
            "comments",
            "min_weight_g",
            "avg_weight_g",
            "max_weight_g",
            "created_at",
            "updated_at",
            "deleted_at",
        ]
        read_only_fields = ["farm", "pond", "created_at", "updated_at"]

    def validate(self, data):
        from apps.batch.models import Batch
        from apps.monitoring.services import CycleStateCalculator

        farm = (
            data.get("farm")
            or (self.instance.farm if self.instance else None)
            or self.context.get("farm")
        )
        pond_id = (
            data.get("pond").id
            if data.get("pond")
            else (self.instance.pond_id if self.instance else None)
        ) or self.context.get("pond_id")
        specie = data.get("specie") or (self.instance.specie if self.instance else None)
        production_plan = data.get("production_plan") or (
            self.instance.production_plan if self.instance else None
        )
        state = data.get("state") or (self.instance.state if self.instance else None)
        start_date = data.get("start_date") or (
            self.instance.start_date if self.instance else None
        )
        estimated_finish_date = data.get("estimated_finish_date") or (
            self.instance.estimated_finish_date if self.instance else None
        )
        finish_date = data.get("finish_date")

        if production_plan and farm and production_plan.farm_id != farm.id:
            raise serializers.ValidationError(
                {
                    "production_plan": "El plan de producción debe pertenecer a la misma granja."
                }
            )

        if production_plan and specie and production_plan.specie_id != specie.id:
            raise serializers.ValidationError(
                {
                    "production_plan": "La especie del plan debe coincidir con la especie del ciclo."
                }
            )

        if production_plan is not None and production_plan.deleted_at is not None:
            raise serializers.ValidationError(
                {
                    "production_plan": "El plan de producción no está disponible (ha sido eliminado)."
                }
            )

        if state in [Cycle.State.IN_PROGRESS, Cycle.State.PAUSED]:
            ciclo_activo = (
                Cycle.objects.filter(
                    pond_id=pond_id,
                    state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
                    deleted_at__isnull=True,
                )
                .exclude(pk=self.instance.pk if self.instance else None)
                .exists()
            )

            if ciclo_activo:
                raise serializers.ValidationError(
                    "Ya existe un ciclo activo en este estanque. "
                    "No se pueden crear dos ciclos activos simultáneamente."
                )

        if start_date and estimated_finish_date:
            if estimated_finish_date <= start_date:
                raise serializers.ValidationError(
                    {
                        "estimated_finish_date": "La fecha estimada de fin debe ser mayor a la fecha de inicio."
                    }
                )

        if finish_date and start_date and finish_date < start_date:
            raise serializers.ValidationError(
                {"finish_date": "La fecha de fin debe ser mayor a la fecha de inicio."}
            )

        if (
            finish_date
            and estimated_finish_date
            and finish_date > estimated_finish_date
        ):
            raise serializers.ValidationError(
                {
                    "finish_date": "La fecha de fin no puede ser mayor a la fecha estimada de fin."
                }
            )

        if state == Cycle.State.FINISHED:
            if not finish_date:
                raise serializers.ValidationError(
                    {
                        "finish_date": "La fecha de fin es obligatoria cuando el ciclo está terminado."
                    }
                )

            # Validar que el ciclo no se puede cambiar a FINISHED directamente sin cosecha
            if self.instance and self.instance.state != Cycle.State.FINISHED:
                raise serializers.ValidationError(
                    {
                        "state": "El ciclo no puede cambiar directamente a estado FINISHED. "
                        "Debe realizarse una cosecha (Harvest) para terminar el ciclo."
                    }
                )

        if finish_date and state not in [Cycle.State.FINISHED, Cycle.State.CANCELLED]:
            raise serializers.ValidationError(
                {
                    "finish_date": "La fecha de fin solo se puede registrar cuando el ciclo está terminado o cancelado."
                }
            )

        return data

    def update(self, instance, validated_data):
        from apps.ponds.models import Pond

        # Verificar si el estado cambió a FINISHED
        new_state = validated_data.get("state", instance.state)
        old_state = instance.state

        # Actualizar la instancia
        instance = super().update(instance, validated_data)

        # Si el ciclo cambió a FINISHED, aplicar el lifecycle centralizado
        if old_state != Cycle.State.FINISHED and new_state == Cycle.State.FINISHED:
            finish_cycle(instance, instance.finish_date)

        # Si el ciclo cambió a CANCELLED, aplicar el lifecycle centralizado
        if old_state != Cycle.State.CANCELLED and new_state == Cycle.State.CANCELLED:
            cancel_cycle(instance, finish_date=instance.finish_date)

        return instance


class CyclePondBatchSerializer(serializers.ModelSerializer):
    pond_batch_detail = PondBatchDetailSerializer(source="pond_batch", read_only=True)

    class Meta:
        model = CyclePondBatch
        fields = [
            "id",
            "cycle",
            "pond_batch",
            "pond_batch_detail",
            "quantity",
            "min_weight_g",
            "avg_weight_g",
            "max_weight_g",
        ]
        read_only_fields = ["min_weight_g", "avg_weight_g", "max_weight_g"]

    def validate(self, data):
        cycle = data.get("cycle")
        pond_batch = data.get("pond_batch")
        quantity = data.get("quantity")

        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError(
                {"quantity": "La cantidad debe ser mayor a 0."}
            )

        if cycle and cycle.state != Cycle.State.IN_PROGRESS:
            raise serializers.ValidationError(
                {"cycle": "Solo se pueden agregar lotes a ciclos en progreso."}
            )

        if pond_batch and pond_batch.end_date is not None:
            raise serializers.ValidationError(
                {
                    "pond_batch": "El PondBatch ya no está activo en el estanque (end_date no es nulo). "
                    "Solo se pueden agregar lotes actualmente presentes en el estanque."
                }
            )

        if pond_batch:
            from apps.ponds.models import Pond

            pond = pond_batch.pond

            # Validar que el estanque esté específicamente en estado "EN USO"
            if pond.status != Pond.Status.IN_USE:
                raise serializers.ValidationError(
                    {
                        "pond_batch": f"El estanque debe estar en estado 'EN USO' para asignar lotes. "
                        f"Estado actual: '{pond.get_status_display()}'."
                    }
                )

        if cycle and pond_batch:
            batch = pond_batch.batch

            # VALIDACIÓN CRÍTICA: El pond_batch debe estar en el MISMO estanque que el ciclo
            if pond_batch.pond_id != cycle.pond_id:
                raise serializers.ValidationError(
                    {
                        "pond_batch": f"El lote debe estar en el MISMO estanque del ciclo. "
                        f"Ciclo en estanque {cycle.pond.code}, "
                        f"pero lote en estanque {pond_batch.pond.code}."
                    }
                )

            # Validar que el pond_batch no esté ya vinculado al ciclo
            existing = CyclePondBatch.objects.filter(cycle=cycle, pond_batch=pond_batch)
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    {"pond_batch": "Este lote ya está vinculado al ciclo."}
                )

            if batch.specie_id != cycle.specie_id:
                raise serializers.ValidationError(
                    {
                        "pond_batch": "La especie del lote no coincide con la especie del ciclo."
                    }
                )

            if batch.farm_id != cycle.farm_id:
                raise serializers.ValidationError(
                    {
                        "pond_batch": "El lote debe pertenecer a la misma granja del ciclo."
                    }
                )

            # Validar que todos los batches del ciclo estén en la misma etapa biológica
            cycle_batches = CyclePondBatch.objects.filter(cycle=cycle)
            if cycle_batches.exists():
                other_batch_biological_state = (
                    cycle_batches.first().pond_batch.batch.biological_state
                )
                if batch.biological_state != other_batch_biological_state:
                    raise serializers.ValidationError(
                        {
                            "pond_batch": f"Todos los lotes del ciclo deben estar en la misma etapa biológica ({other_batch_biological_state}). Este lote está en {batch.biological_state}."
                        }
                    )

        return data

    def create(self, validated_data):
        """
        Crea una asociación de lote a ciclo calculando automáticamente los pesos
        desde el pond_batch.
        """
        from apps.monitoring.services import BiomassCalculator

        pond_batch = validated_data.get("pond_batch")

        # Calcular pesos desde el pond_batch
        pond = pond_batch.pond
        weights = BiomassCalculator.get_active_pond_weights(pond.id)

        validated_data["min_weight_g"] = weights["min_weight_g"]
        validated_data["avg_weight_g"] = weights["avg_weight_g"]
        validated_data["max_weight_g"] = weights["max_weight_g"]

        return super().create(validated_data)
