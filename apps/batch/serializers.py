from datetime import date

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from apps.ponds.models import Pond

from .models import Batch, BatchSource, BatchTransfer, PondBatch


class BatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Batch
        fields = [
            "id",
            "specie",
            "farm",
            "origin_type",
            "origin_id",
            "code",
            "biological_state",
            "status",
            "comments",
            "initial_quantity",
            "min_weight_g",
            "avg_weight_g",
            "max_weight_g",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["code", "created_at", "updated_at"]

    def validate(self, data):
        if self.instance is not None:
            from apps.cycle.models import Cycle, CyclePondBatch

            if CyclePondBatch.objects.filter(
                pond_batch__batch=self.instance,
                cycle__state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
            ).exists():
                raise serializers.ValidationError(
                    "El lote pertenece a un ciclo en proceso y no se puede editar "
                    "manualmente. Sus cambios deben provenir de eventos del ciclo."
                )

        min_weight = data.get("min_weight_g")
        avg_weight = data.get("avg_weight_g")
        max_weight = data.get("max_weight_g")

        if min_weight and avg_weight and max_weight:
            if not (min_weight <= avg_weight <= max_weight):
                raise serializers.ValidationError(
                    {
                        "weights": "min_weight_g <= avg_weight_g <= max_weight_g debe cumplirse."
                    }
                )

        origin_type = data.get("origin_type")
        origin_id = data.get("origin_id")

        if origin_type in [
            Batch.OriginType.PURCHASE_DETAIL,
            Batch.OriginType.HARVEST_CLASSIFICATION,
        ]:
            if not origin_id:
                raise serializers.ValidationError(
                    {"origin_id": f"origin_id es obligatorio para {origin_type}."}
                )

        return data

    def create(self, validated_data):
        farm = validated_data["farm"]
        timestamp = int(timezone.now().timestamp())
        code = f"BATCH-{farm.id}-{timestamp}"

        while Batch.objects.filter(code=code, farm=farm).exists():
            timestamp += 1
            code = f"BATCH-{farm.id}-{timestamp}"

        validated_data["code"] = code
        return super().create(validated_data)


class BatchSplitSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=500)

    def validate(self, data):
        batch = self.context["batch"]
        quantity = data["quantity"]

        if batch.status != Batch.Status.ACTIVE:
            raise serializers.ValidationError(
                {"batch": "Solo se puede dividir un lote activo."}
            )
        if PondBatch.objects.filter(batch=batch).exists():
            raise serializers.ValidationError(
                {
                    "batch": (
                        "El lote ya fue asignado a un estanque. Utiliza la "
                        "transferencia desde el estanque para dividirlo."
                    )
                }
            )
        if quantity >= batch.initial_quantity:
            raise serializers.ValidationError(
                {
                    "quantity": (
                        "La cantidad separada debe ser menor que la cantidad total "
                        f"del lote ({batch.initial_quantity})."
                    )
                }
            )
        return data

    @transaction.atomic
    def create(self, validated_data):
        batch = Batch.objects.select_for_update().get(pk=self.context["batch"].pk)
        quantity = validated_data["quantity"]
        reason = validated_data["reason"].strip()

        if PondBatch.objects.filter(batch=batch).exists():
            raise serializers.ValidationError(
                {"batch": "El lote fue asignado mientras se procesaba la división."}
            )
        if quantity <= 0 or quantity >= batch.initial_quantity:
            raise serializers.ValidationError(
                {"quantity": "La disponibilidad cambió; vuelve a consultar el lote."}
            )

        original_quantity = batch.initial_quantity
        retained_quantity = original_quantity - quantity
        timestamp = int(timezone.now().timestamp())
        base_code = f"{batch.code[:30]}-D{timestamp}"
        child_code = base_code[:50]
        suffix = 1
        while Batch.objects.filter(farm=batch.farm, code=child_code).exists():
            suffix += 1
            child_code = f"{base_code[:45]}-{suffix}"[:50]

        child = Batch.objects.create(
            farm=batch.farm,
            specie=batch.specie,
            origin_type=Batch.OriginType.BATCH_SPLIT,
            origin_id=batch.pk,
            code=child_code,
            biological_state=batch.biological_state,
            status=Batch.Status.ACTIVE,
            comments=f"División previa a asignación. Motivo: {reason}",
            initial_quantity=quantity,
            min_weight_g=batch.min_weight_g,
            avg_weight_g=batch.avg_weight_g,
            max_weight_g=batch.max_weight_g,
        )
        BatchSource.objects.create(
            parent_batch=batch,
            child_batch=child,
            quantity=quantity,
        )
        batch.initial_quantity = retained_quantity
        batch.save(update_fields=["initial_quantity", "updated_at"])

        return {
            "parent_batch": BatchSerializer(batch).data,
            "child_batch": BatchSerializer(child).data,
            "original_quantity": original_quantity,
            "retained_quantity": retained_quantity,
            "split_quantity": quantity,
            "genealogy": {
                "parent_batch_id": batch.pk,
                "child_batch_id": child.pk,
            },
            "reason": reason,
        }


class BatchSplitResultSerializer(serializers.Serializer):
    parent_batch = BatchSerializer()
    child_batch = BatchSerializer()
    original_quantity = serializers.IntegerField()
    retained_quantity = serializers.IntegerField()
    split_quantity = serializers.IntegerField()
    genealogy = serializers.DictField()
    reason = serializers.CharField()


class BatchSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchSource
        fields = ["id", "parent_batch", "child_batch", "quantity"]

    def validate(self, data):
        if data["parent_batch"] == data["child_batch"]:
            raise serializers.ValidationError(
                "Un lote no puede ser su propio padre o hijo."
            )
        if data["quantity"] <= 0:
            raise serializers.ValidationError(
                {"quantity": "La cantidad debe ser mayor a 0."}
            )
        return data


class PondBatchSerializer(serializers.ModelSerializer):
    split_result = serializers.SerializerMethodField()

    class Meta:
        model = PondBatch
        fields = [
            "id",
            "pond",
            "batch",
            "initial_quantity",
            "current_quantity",
            "start_date",
            "end_date",
            "split_result",
        ]
        read_only_fields = ["current_quantity"]

    def get_split_result(self, instance) -> dict | None:
        return getattr(instance, "_split_result", None)

    def validate(self, data):
        if self.instance is not None:
            from apps.cycle.models import Cycle, CyclePondBatch

            if CyclePondBatch.objects.filter(
                pond_batch=self.instance,
                cycle__state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
            ).exists():
                raise serializers.ValidationError(
                    "La asignación del lote al estanque pertenece a un ciclo en "
                    "proceso y no se puede editar manualmente."
                )

        pond = data.get("pond") or (self.instance.pond if self.instance else None)
        batch = data.get("batch") or (self.instance.batch if self.instance else None)
        cantidad_nueva = data.get(
            "initial_quantity",
            self.instance.initial_quantity if self.instance else 0,
        )
        start_date = data.get(
            "start_date", self.instance.start_date if self.instance else None
        )
        end_date = data.get(
            "end_date", self.instance.end_date if self.instance else None
        )

        if pond and pond.deleted_at is not None:
            raise serializers.ValidationError(
                {"pond": "El estanque ha sido eliminado y no está disponible."}
            )

        # Validar que el estanque esté en estado ACTIVE o IN_USE
        if pond and pond.status not in [pond.Status.ACTIVE, pond.Status.IN_USE]:
            raise serializers.ValidationError(
                {
                    "pond": f"Solo se pueden agregar lotes a estanques en estado ACTIVO o EN USO. "
                    f"Estado actual: '{pond.get_status_display()}'."
                }
            )

        if batch and batch.status != Batch.Status.ACTIVE:
            raise serializers.ValidationError(
                {
                    "batch": f"El lote no está activo. Estado actual: '{batch.get_status_display()}'."
                }
            )

        if self.instance is None and batch:
            if cantidad_nueva > batch.initial_quantity:
                raise serializers.ValidationError(
                    {
                        "initial_quantity": (
                            f"La cantidad excede la disponible en el lote "
                            f"({batch.initial_quantity})."
                        )
                    }
                )
            if (
                cantidad_nueva < batch.initial_quantity
                and PondBatch.objects.filter(batch=batch).exists()
            ):
                raise serializers.ValidationError(
                    {
                        "initial_quantity": (
                            "La división automática solo aplica antes de la primera "
                            "asignación del lote."
                        )
                    }
                )

        if batch:
            asignaciones_activas = PondBatch.objects.filter(
                batch=batch, end_date__isnull=True
            )
            if self.instance:
                asignaciones_activas = asignaciones_activas.exclude(pk=self.instance.pk)

            if asignaciones_activas.exists():
                raise serializers.ValidationError(
                    {"batch": "El lote ya está asignado a un estanque activo."}
                )

        if pond and batch and pond.farm_id != batch.farm_id:
            raise serializers.ValidationError(
                {"pond": "El estanque debe pertenecer a la misma granja del lote."}
            )

        if pond and batch:
            active_pond_batches = (
                PondBatch.objects.filter(
                    pond=pond,
                    end_date__isnull=True,
                    current_quantity__gt=0,
                    batch__status=Batch.Status.ACTIVE,
                ).select_related("batch", "batch__specie")
            )
            if self.instance:
                active_pond_batches = active_pond_batches.exclude(pk=self.instance.pk)

            other_species = active_pond_batches.exclude(
                batch__specie_id=batch.specie_id
            ).first()

            if other_species:
                raise serializers.ValidationError(
                    {
                        "batch": "No se puede combinar lotes de especies distintas en un mismo estanque. "
                        f"El estanque ya tiene un lote de la especie '{other_species.batch.specie}'."
                    }
                )

            different_biological_state = (
                active_pond_batches.filter(batch__specie_id=batch.specie_id)
                .exclude(batch__biological_state=batch.biological_state)
                .first()
            )

            if different_biological_state:
                raise serializers.ValidationError(
                    {
                        "batch": f"No se puede asignar el lote al estanque porque la especie coincide "
                        f"pero el estado biológico no. Lote nuevo: "
                        f"'{batch.get_biological_state_display()}'; lote existente: "
                        f"'{different_biological_state.batch.get_biological_state_display()}'. "
                        "Para convivir en el mismo estanque, especie y estado biológico deben coincidir."
                    }
                )

        if start_date and start_date > date.today():
            raise serializers.ValidationError(
                {"start_date": "La fecha de inicio no puede ser futura."}
            )

        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(
                {
                    "end_date": "La fecha de fin debe ser mayor o igual a la fecha de inicio."
                }
            )

        cantidad_actual_qs = PondBatch.objects.filter(pond=pond, end_date__isnull=True)
        if self.instance:
            cantidad_actual_qs = cantidad_actual_qs.exclude(pk=self.instance.pk)

        cantidad_actual = cantidad_actual_qs.aggregate(total=Sum("current_quantity"))[
            "total"
        ] or 0

        if cantidad_actual + cantidad_nueva > pond.capacity:
            raise serializers.ValidationError(
                {
                    "initial_quantity": f"El estanque '{pond.name}' supera su capacidad de "
                    f"{pond.capacity} peces. Disponible: {pond.capacity - cantidad_actual}."
                }
            )

        return data

    @transaction.atomic
    def create(self, validated_data):
        batch = Batch.objects.select_for_update().get(pk=validated_data["batch"].pk)
        assigned_quantity = validated_data["initial_quantity"]
        split_result = None

        if assigned_quantity > batch.initial_quantity:
            raise serializers.ValidationError(
                {"initial_quantity": "La disponibilidad cambió; vuelve a consultar el lote."}
            )

        has_previous_assignment = PondBatch.objects.filter(batch=batch).exists()
        remainder = batch.initial_quantity - assigned_quantity
        if remainder and not has_previous_assignment:
            original_quantity = batch.initial_quantity
            timestamp = int(timezone.now().timestamp())
            base_code = f"{batch.code[:30]}-R{timestamp}"
            child_code = base_code[:50]
            suffix = 1
            while Batch.objects.filter(farm=batch.farm, code=child_code).exists():
                suffix += 1
                child_code = f"{base_code[:45]}-{suffix}"[:50]

            child = Batch.objects.create(
                farm=batch.farm,
                specie=batch.specie,
                origin_type=Batch.OriginType.BATCH_SPLIT,
                origin_id=batch.pk,
                code=child_code,
                biological_state=batch.biological_state,
                status=Batch.Status.ACTIVE,
                comments=(
                    "Remanente disponible tras asignación parcial del lote "
                    f"{batch.code} a un estanque."
                ),
                initial_quantity=remainder,
                min_weight_g=batch.min_weight_g,
                avg_weight_g=batch.avg_weight_g,
                max_weight_g=batch.max_weight_g,
            )
            BatchSource.objects.create(
                parent_batch=batch,
                child_batch=child,
                quantity=remainder,
            )
            batch.initial_quantity = assigned_quantity
            batch.save(update_fields=["initial_quantity", "updated_at"])
            split_result = {
                "was_split": True,
                "original_quantity": original_quantity,
                "assigned_batch": BatchSerializer(batch).data,
                "assigned_quantity": assigned_quantity,
                "remainder_batch": BatchSerializer(child).data,
                "remainder_quantity": remainder,
                "genealogy": {
                    "parent_batch_id": batch.pk,
                    "child_batch_id": child.pk,
                },
            }
        elif remainder and has_previous_assignment:
            raise serializers.ValidationError(
                {
                    "initial_quantity": (
                        "No se puede dividir parcialmente un lote con asignaciones previas."
                    )
                }
            )

        validated_data["batch"] = batch
        validated_data["current_quantity"] = assigned_quantity
        pond_batch = super().create(validated_data)
        pond_batch._split_result = split_result

        # Cambiar el estado del estanque a IN_USE
        pond = pond_batch.pond
        if pond.status == pond.Status.ACTIVE:
            pond.status = pond.Status.IN_USE
            pond.save(update_fields=["status"])

        return pond_batch


class BatchTransferSerializer(serializers.ModelSerializer):
    destination_pond = serializers.PrimaryKeyRelatedField(
        queryset=Pond.objects.filter(deleted_at__isnull=True),
        write_only=True,
    )
    source_pond_id = serializers.IntegerField(
        source="source_pond_batch.pond_id", read_only=True
    )
    source_pond_name = serializers.CharField(
        source="source_pond_batch.pond.name", read_only=True
    )
    destination_pond_id = serializers.IntegerField(
        source="to_pond_batch.pond_id", read_only=True
    )
    destination_pond_name = serializers.CharField(
        source="to_pond_batch.pond.name", read_only=True
    )
    source_batch_id = serializers.IntegerField(
        source="source_pond_batch.batch_id", read_only=True
    )
    source_batch_code = serializers.CharField(
        source="source_pond_batch.batch.code", read_only=True
    )
    destination_batch_id = serializers.IntegerField(
        source="to_pond_batch.batch_id", read_only=True
    )
    destination_batch_code = serializers.CharField(
        source="to_pond_batch.batch.code", read_only=True
    )
    is_partial = serializers.SerializerMethodField()

    class Meta:
        model = BatchTransfer
        fields = [
            "id",
            "source_pond_batch",
            "to_pond_batch",
            "destination_pond",
            "farm",
            "quantity",
            "date",
            "reason",
            "source_pond_id",
            "source_pond_name",
            "destination_pond_id",
            "destination_pond_name",
            "source_batch_id",
            "source_batch_code",
            "destination_batch_id",
            "destination_batch_code",
            "is_partial",
        ]
        read_only_fields = ["to_pond_batch", "farm"]

    def get_is_partial(self, instance) -> bool:
        return (
            instance.source_pond_batch.batch_id
            != instance.to_pond_batch.batch_id
        )

    def _farm_id(self):
        view = self.context.get("view")
        return int(view.kwargs["farm_pk"]) if view else None

    def validate(self, data):
        from apps.cycle.models import Cycle, CyclePondBatch

        source = data["source_pond_batch"]
        destination = data["destination_pond"]
        quantity = data["quantity"]
        transfer_date = data.get("date")
        farm_id = self._farm_id()

        if quantity <= 0:
            raise serializers.ValidationError(
                {"quantity": "La cantidad debe ser mayor a 0."}
            )

        if transfer_date and transfer_date > date.today():
            raise serializers.ValidationError(
                {"date": "La fecha de transferencia no puede ser futura."}
            )

        if source.end_date is not None or source.current_quantity <= 0:
            raise serializers.ValidationError(
                {"source_pond_batch": "El lote ya no está activo en el estanque origen."}
            )

        if farm_id and (
            source.batch.farm_id != farm_id or destination.farm_id != farm_id
        ):
            raise serializers.ValidationError(
                {"destination_pond": "Origen y destino deben pertenecer a esta granja."}
            )

        if source.pond_id == destination.pk:
            raise serializers.ValidationError(
                {
                    "destination_pond": "El estanque origen y destino no pueden ser el mismo."
                }
            )

        # Validar que AMBOS estanques están INACTIVOS (sin ciclos activos)
        source_has_active_cycle = CyclePondBatch.objects.filter(
            pond_batch=source,
            cycle__state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
        ).exists()

        if source_has_active_cycle:
            raise serializers.ValidationError(
                {
                    "source_pond_batch": "El lote pertenece a un ciclo activo o pausado y no se puede transferir manualmente."
                }
            )

        dest_has_active_cycle = Cycle.objects.filter(
            pond=destination,
            deleted_at__isnull=True,
            state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
        ).exists()

        if dest_has_active_cycle:
            raise serializers.ValidationError(
                {
                    "destination_pond": "El estanque destino tiene un ciclo activo o pausado."
                }
            )

        if destination.status not in [Pond.Status.ACTIVE, Pond.Status.IN_USE]:
            raise serializers.ValidationError(
                {"destination_pond": "El estanque destino debe estar activo o en uso."}
            )

        if source.batch.status != Batch.Status.ACTIVE:
            raise serializers.ValidationError(
                {
                    "source_pond_batch": f"El lote no está activo. Estado actual: '{source.batch.get_status_display()}'."
                }
            )

        if source.current_quantity < quantity:
            raise serializers.ValidationError(
                {
                    "quantity": f"Cantidad insuficiente. Disponible: {source.current_quantity}."
                }
            )

        incompatible = (
            PondBatch.objects.filter(
                pond=destination,
                end_date__isnull=True,
                current_quantity__gt=0,
                batch__status=Batch.Status.ACTIVE,
            )
            .exclude(
                batch__specie_id=source.batch.specie_id,
                batch__biological_state=source.batch.biological_state,
            )
            .exists()
        )
        if incompatible:
            raise serializers.ValidationError(
                {
                    "destination_pond": "El estanque destino contiene peces de otra especie o etapa biológica."
                }
            )

        cantidad_actual_destino = (
            PondBatch.objects.filter(
                pond=destination, end_date__isnull=True
            ).aggregate(total=Sum("current_quantity"))["total"]
            or 0
        )

        if cantidad_actual_destino + quantity > destination.capacity:
            raise serializers.ValidationError(
                {
                    "destination_pond": f"El estanque destino '{destination.name}' supera su capacidad de "
                    f"{destination.capacity} peces. "
                    f"Disponible: {destination.capacity - cantidad_actual_destino}."
                }
            )

        return data

    @transaction.atomic
    def create(self, validated_data):
        source = (
            PondBatch.objects.select_for_update()
            .select_related("batch", "pond")
            .get(pk=validated_data["source_pond_batch"].pk)
        )
        destination = Pond.objects.select_for_update().get(
            pk=validated_data.pop("destination_pond").pk
        )
        quantity = validated_data["quantity"]
        transfer_date = validated_data["date"]

        if source.end_date is not None or quantity > source.current_quantity:
            raise serializers.ValidationError(
                {"quantity": "La disponibilidad cambió; vuelve a consultar el lote."}
            )

        occupied = (
            PondBatch.objects.filter(
                pond=destination, end_date__isnull=True
            ).aggregate(total=Sum("current_quantity"))["total"]
            or 0
        )
        if occupied + quantity > destination.capacity:
            raise serializers.ValidationError(
                {"destination_pond": "La capacidad disponible del estanque cambió."}
            )

        incompatible = (
            PondBatch.objects.filter(
                pond=destination,
                end_date__isnull=True,
                current_quantity__gt=0,
                batch__status=Batch.Status.ACTIVE,
            )
            .exclude(
                batch__specie_id=source.batch.specie_id,
                batch__biological_state=source.batch.biological_state,
            )
            .exists()
        )
        if incompatible:
            raise serializers.ValidationError(
                {
                    "destination_pond": (
                        "El estanque destino cambió y ahora contiene peces de otra "
                        "especie o etapa biológica."
                    )
                }
            )

        source_batch = source.batch
        is_partial = quantity < source.current_quantity
        destination_batch = source_batch

        if is_partial:
            timestamp = int(timezone.now().timestamp())
            base_code = f"{source_batch.code[:30]}-T{timestamp}"
            code = base_code[:50]
            suffix = 1
            while Batch.objects.filter(farm=source_batch.farm, code=code).exists():
                suffix += 1
                code = f"{base_code[:45]}-{suffix}"[:50]

            destination_batch = Batch.objects.create(
                farm=source_batch.farm,
                specie=source_batch.specie,
                origin_type=Batch.OriginType.BATCH_SPLIT,
                origin_id=source_batch.pk,
                code=code,
                biological_state=source_batch.biological_state,
                status=Batch.Status.ACTIVE,
                comments=f"Derivado por transferencia manual desde {source.pond.name}.",
                initial_quantity=quantity,
                min_weight_g=source_batch.min_weight_g,
                avg_weight_g=source_batch.avg_weight_g,
                max_weight_g=source_batch.max_weight_g,
            )
            BatchSource.objects.create(
                parent_batch=source_batch,
                child_batch=destination_batch,
                quantity=quantity,
            )

        source.current_quantity -= quantity
        source_fields = ["current_quantity"]
        if source.current_quantity == 0:
            source.end_date = transfer_date
            source_fields.append("end_date")
        source.save(update_fields=source_fields)

        destination_assignment = PondBatch.objects.create(
            pond=destination,
            batch=destination_batch,
            initial_quantity=quantity,
            current_quantity=quantity,
            start_date=transfer_date,
        )

        if destination.status == Pond.Status.ACTIVE:
            destination.status = Pond.Status.IN_USE
            destination.save(update_fields=["status"])

        if source.current_quantity == 0 and not PondBatch.objects.filter(
            pond=source.pond,
            end_date__isnull=True,
            current_quantity__gt=0,
        ).exists():
            source.pond.status = Pond.Status.ACTIVE
            source.pond.save(update_fields=["status"])

        validated_data["source_pond_batch"] = source
        validated_data["to_pond_batch"] = destination_assignment
        return BatchTransfer.objects.create(**validated_data)

