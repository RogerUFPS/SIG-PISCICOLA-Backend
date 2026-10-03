from datetime import date, timedelta

from django.db import transaction
from rest_framework import serializers

from apps.batch.models import Batch, PondBatch
from apps.cycle.models import Cycle, CyclePondBatch
from apps.ponds.models import Pond
from apps.products.models import Product
from apps.purchases.models import InventoryMovement
from apps.purchases.utils import create_out_movement

from .models import ControlStat, DailyStat, FishEvaluated, ProductUsageLog
from .services import BiomassCalculator, FishEvaluatedCalculator


class FishEvaluatedSerializer(serializers.ModelSerializer):
    """
    Serializer para evaluaciones de peces con validaciones completas.

    Usuario envía:
    - min_weight_g, max_weight_g: Pesos medidos en el muestreo

    Backend calcula automáticamente:
    - avg_weight_g = (min_weight_g + max_weight_g) / 2
    """

    batch_id = serializers.IntegerField(write_only=True, required=False)
    live_quantity = serializers.SerializerMethodField()
    biomass_kg = serializers.SerializerMethodField()

    class Meta:
        model = FishEvaluated
        fields = [
            "id",
            "cycle",
            "pond",
            "evaluation_date",
            "sampled_quantity",
            "min_weight_g",
            "avg_weight_g",
            "max_weight_g",
            "mortality_quantity",
            "live_quantity",
            "biomass_kg",
            "observations",
            "batch_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "cycle",
            "pond",
            "avg_weight_g",
            "live_quantity",
            "biomass_kg",
            "created_at",
            "updated_at",
        ]

    #    def _calculate_evaluation_biomass(self, obj):
    #        sample_live_quantity = BiomassCalculator.get_sample_live_quantity(
    #            obj.sampled_quantity,
    #            obj.mortality_quantity,
    #        )
    #        return BiomassCalculator.calculate_control_biomass(
    #            obj.cycle_id,
    #            obj.pond_id,
    #            obj.avg_weight_g,
    #            mortality_quantity=obj.mortality_quantity,
    #            fallback_live_quantity=sample_live_quantity,
    #        )

    #    def get_live_quantity(self, obj):
    #        live_quantity, _ = self._calculate_evaluation_biomass(obj)
    #        return live_quantity
    #
    #    def get_biomass_kg(self, obj):
    #        _, biomass_kg = self._calculate_evaluation_biomass(obj)
    #        return biomass_kg

    def _resolve_cycle_and_pond(self, data):
        """
        cycle/pond son read_only, por eso no vienen en `data` al crear.
        Se buscan en: data -> instance -> context -> initial_data.
        """
        cycle = data.get("cycle") or (self.instance.cycle if self.instance else None)
        pond = data.get("pond") or (self.instance.pond if self.instance else None)

        if cycle is None:
            cycle = self.context.get("cycle")
        if pond is None:
            pond = self.context.get("pond")

        initial = getattr(self, "initial_data", {}) or {}
        if cycle is None:
            cycle_id = initial.get("cycle") or initial.get("cycle_id")
            if cycle_id:
                cycle = Cycle.objects.filter(id=cycle_id).first()
        if pond is None:
            pond_id = initial.get("pond") or initial.get("pond_id")
            if pond_id:
                pond = Pond.objects.filter(id=pond_id).first()

        # Cada ciclo es de UN solo estanque: si falta pond, se toma del ciclo
        if pond is None and cycle is not None:
            pond = cycle.pond

        return cycle, pond

    def _get_available_live_quantity(self, cycle, pond):
        """
        Peces vivos disponibles ANTES de aplicar esta evaluación.
        Fuente principal: último ControlStat del ciclo/estanque.
        Fallback (no hay ControlStat aún): suma de current_quantity de los PondBatch activos.
        """
        last_control = (
            ControlStat.objects.filter(
                cycle_id=cycle.id,
                pond_id=pond.id,
                deleted_at__isnull=True,
            )
            .order_by("-control_date", "-id")
            .first()
        )

        if last_control is not None:
            live_available = last_control.live_quantity
            # En update, si el ControlStat más reciente es el de esta misma
            # evaluación, su live_quantity ya descontó su mortalidad: se devuelve.
            if (
                self.instance
                and last_control.control_date == self.instance.evaluation_date
            ):
                live_available += self.instance.mortality_quantity
            return live_available

        cpbs = self._get_active_cycle_pond_batches(cycle, pond)
        live_available = sum(cpb.pond_batch.current_quantity for cpb in cpbs)
        if self.instance:
            live_available += self.instance.mortality_quantity
        return live_available

    def _get_control_stat(self, obj):
        return ControlStat.objects.filter(
            cycle_id=obj.cycle_id,
            pond_id=obj.pond_id,
            control_date=obj.evaluation_date,
            deleted_at__isnull=True,
        ).first()

    def get_live_quantity(self, obj):
        cs = self._get_control_stat(obj)
        if cs:
            return cs.live_quantity
        return BiomassCalculator.get_sample_live_quantity(
            obj.sampled_quantity, obj.mortality_quantity
        )

    def get_biomass_kg(self, obj):
        cs = self._get_control_stat(obj)
        if cs:
            return cs.biomass_kg
        live_qty = BiomassCalculator.get_cycle_pond_live_quantity(
            obj.cycle_id, obj.pond_id
        )
        if live_qty <= 0:
            live_qty = BiomassCalculator.get_sample_live_quantity(
                obj.sampled_quantity, obj.mortality_quantity
            )
        return BiomassCalculator.calculate_biomass(live_qty, obj.avg_weight_g)

    def _get_active_cycle_pond_batches(self, cycle, pond):
        return list(
            CyclePondBatch.objects.filter(
                cycle=cycle,
                pond_batch__pond=pond,
                pond_batch__end_date__isnull=True,
            )
            .select_related("pond_batch", "pond_batch__batch")
            .order_by("id")
        )

    def _get_mortality_targets(self, cycle, pond, batch_id=None):
        cycle_pond_batches = self._get_active_cycle_pond_batches(cycle, pond)
        if not cycle_pond_batches:
            raise serializers.ValidationError(
                {
                    "mortality_quantity": (
                        "No hay lotes activos del ciclo en este estanque para "
                        "descontar mortalidad."
                    )
                }
            )

        pond_batches = [cpb.pond_batch for cpb in cycle_pond_batches]
        if batch_id:
            pond_batches = [pb for pb in pond_batches if pb.batch_id == batch_id]
            if not pond_batches:
                raise serializers.ValidationError(
                    {
                        "batch_id": (
                            "El lote especificado no está activo en este ciclo y "
                            "estanque."
                        )
                    }
                )

        return pond_batches

    def _distribute_quantity(self, quantity, pond_batches, *, by_current_stock=True):
        if quantity <= 0:
            return []

        if by_current_stock:
            total_quantity = sum(pb.current_quantity for pb in pond_batches)
        else:
            total_quantity = 0

        if total_quantity <= 0:
            base = quantity // len(pond_batches)
            remainder = quantity - (base * len(pond_batches))
            return [
                (pb, base + (1 if index < remainder else 0))
                for index, pb in enumerate(pond_batches)
            ]

        reductions = []
        total_reduced = 0
        for pond_batch in pond_batches:
            exact = quantity * (pond_batch.current_quantity / total_quantity)
            reduce_int = int(exact)
            reductions.append(
                {
                    "pond_batch": pond_batch,
                    "quantity": reduce_int,
                    "remainder": exact - reduce_int,
                }
            )
            total_reduced += reduce_int

        remaining = quantity - total_reduced
        for reduction in sorted(
            reductions, key=lambda item: item["remainder"], reverse=True
        )[:remaining]:
            reduction["quantity"] += 1

        return [
            (reduction["pond_batch"], reduction["quantity"]) for reduction in reductions
        ]

    def _apply_mortality_stock_change(
        self, *, cycle, pond, quantity, batch_id=None, restore=False
    ):
        if quantity <= 0:
            return

        pond_batches = self._get_mortality_targets(cycle, pond, batch_id=batch_id)

        if restore:
            changes = self._distribute_quantity(
                quantity, pond_batches, by_current_stock=True
            )
            for pond_batch, quantity_to_add in changes:
                if quantity_to_add <= 0:
                    continue
                pond_batch.current_quantity += quantity_to_add
                pond_batch.save(update_fields=["current_quantity"])
            return

        total_available = sum(pb.current_quantity for pb in pond_batches)
        if quantity > total_available:
            raise serializers.ValidationError(
                {
                    "mortality_quantity": (
                        f"La mortalidad indicada ({quantity}) supera los peces "
                        f"vivos disponibles ({total_available})."
                    )
                }
            )

        changes = self._distribute_quantity(quantity, pond_batches)
        for pond_batch, quantity_to_reduce in changes:
            if quantity_to_reduce <= 0:
                continue
            pond_batch.current_quantity -= quantity_to_reduce
            pond_batch.save(update_fields=["current_quantity"])

    def _refresh_cycle_control_stat(self, fish_evaluated, *, ignore_same_day=False):
        cycle = fish_evaluated.cycle
        pond = fish_evaluated.pond
        evaluation_date = fish_evaluated.evaluation_date

        sample_live_quantity = BiomassCalculator.get_sample_live_quantity(
            fish_evaluated.sampled_quantity,
            fish_evaluated.mortality_quantity,
        )
        live_quantity, biomass_kg = BiomassCalculator.calculate_control_biomass(
            cycle.id,
            pond.id,
            fish_evaluated.avg_weight_g,
            mortality_quantity=fish_evaluated.mortality_quantity,
            fallback_live_quantity=sample_live_quantity,
        )
        mortality_percentage = (
            fish_evaluated.mortality_quantity / fish_evaluated.sampled_quantity * 100
            if fish_evaluated.sampled_quantity > 0
            else 0.0
        )

        if ignore_same_day:
            previous_control = (
                ControlStat.objects.filter(
                    cycle_id=cycle.id,
                    pond_id=pond.id,
                    control_date__lt=evaluation_date,
                    deleted_at__isnull=True,
                )
                .order_by("-control_date")
                .first()
            )
        else:
            previous_control = BiomassCalculator.get_previous_control_stat(
                cycle.id, pond.id, evaluation_date
            )

        biomass_gain_kg = None
        fca = None

        if previous_control is not None:
            biomass_gain_kg = BiomassCalculator.calculate_biomass_gain(
                biomass_kg, previous_control.biomass_kg
            )
            from apps.feeding.utils import cycle_feed_consumed_kg

            alimento_kg = cycle_feed_consumed_kg(
                cycle_id=cycle.id,
                start_date=previous_control.control_date,
                end_date=evaluation_date,
            )
            fca = BiomassCalculator.calculate_fca(float(alimento_kg), biomass_gain_kg)

        ControlStat.objects.update_or_create(
            cycle=cycle,
            pond=pond,
            control_date=evaluation_date,
            defaults={
                "farm": cycle.farm,
                "sampled_quantity": fish_evaluated.sampled_quantity,
                "live_quantity": live_quantity,
                "min_weight_g": fish_evaluated.min_weight_g,
                "avg_weight_g": fish_evaluated.avg_weight_g,
                "max_weight_g": fish_evaluated.max_weight_g,
                "mortality_percentage": mortality_percentage,
                "biomass_kg": biomass_kg,
                "biomass_gain_kg": biomass_gain_kg,
                "fca": fca,
                "deleted_at": None,
            },
        )
    def validate(self, data):
        cycle, pond = self._resolve_cycle_and_pond(data)

        evaluation_date = data.get(
            "evaluation_date",
            self.instance.evaluation_date if self.instance else None,
        )
        sampled_quantity = data.get(
            "sampled_quantity",
            self.instance.sampled_quantity if self.instance else None,
        )
        mortality_quantity = data.get(
            "mortality_quantity",
            self.instance.mortality_quantity if self.instance else 0,
        )
        batch_id = data.get("batch_id")

        # En creación, cycle y pond son obligatorios para poder validar
        if not self.instance:
            if cycle is None:
                raise serializers.ValidationError(
                    {"cycle": "No se pudo determinar el ciclo de la evaluación."}
                )
            if pond is None:
                raise serializers.ValidationError(
                    {"pond": "No se pudo determinar el estanque de la evaluación."}
                )

        # Ciclo IN_PROGRESS
        if cycle and cycle.state != Cycle.State.IN_PROGRESS:
            raise serializers.ValidationError(
                {"cycle": "El ciclo debe estar en estado IN_PROGRESS."}
            )

        # Estanque IN_USE
        if pond and pond.status != Pond.Status.IN_USE:
            raise serializers.ValidationError(
                {"pond": "El estanque debe estar en estado IN_USE."}
            )

        # Estanque asociado al ciclo
        active_cpbs = []
        if cycle and pond:
            active_cpbs = self._get_active_cycle_pond_batches(cycle, pond)
            if not active_cpbs:
                raise serializers.ValidationError(
                    {"pond": "El estanque no está asociado a este ciclo."}
                )

        # Cantidad muestreada > 0
        if sampled_quantity is not None and sampled_quantity <= 0:
            raise serializers.ValidationError(
                {"sampled_quantity": "La cantidad de peces evaluados debe ser mayor a 0."}
            )

        # Mortalidad <= muestra
        if (
            sampled_quantity is not None
            and mortality_quantity is not None
            and mortality_quantity > sampled_quantity
        ):
            raise serializers.ValidationError(
                {"mortality_quantity": "La mortalidad no puede ser mayor a la cantidad muestreada."}
            )

        # Fecha <= hoy
        if evaluation_date and evaluation_date > date.today():
            raise serializers.ValidationError(
                {"evaluation_date": "La fecha de evaluación no puede ser futura."}
            )

        # batch_id existe y está activo en este ciclo/estanque
        if batch_id:
            if not Batch.objects.filter(id=batch_id).exists():
                raise serializers.ValidationError(
                    {"batch_id": "El batch especificado no existe."}
                )
            if active_cpbs and not any(
                cpb.pond_batch.batch_id == batch_id for cpb in active_cpbs
            ):
                raise serializers.ValidationError(
                    {"batch_id": "El lote especificado no está activo en este ciclo y estanque."}
                )

        # Muestra <= peces vivos (según ControlStat)
        if cycle and pond and sampled_quantity is not None:
            live_available = self._get_available_live_quantity(cycle, pond)
            if sampled_quantity > live_available:
                raise serializers.ValidationError(
                    {
                        "sampled_quantity": (
                            f"La cantidad muestreada ({sampled_quantity}) supera "
                            f"los peces vivos disponibles ({live_available})."
                        )
                    }
                )

        return data

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        ✓ NUEVA VALIDACIÓN: Prohibir editar evaluaciones de ciclos terminados
        """
        # Verificar que el ciclo NO esté en estado FINISHED o CANCELLED
        if instance.cycle.state in [Cycle.State.FINISHED, Cycle.State.CANCELLED]:
            raise serializers.ValidationError(
                {
                    "detail": "No se puede editar registros de monitoreo de ciclos que ya están terminados o cancelados."
                }
            )

        # Proceder con la actualización
        batch_id = validated_data.pop("batch_id", None)
        previous_mortality = instance.mortality_quantity

        min_weight = validated_data.get("min_weight_g", instance.min_weight_g)
        max_weight = validated_data.get("max_weight_g", instance.max_weight_g)
        validated_data["avg_weight_g"] = (min_weight + max_weight) / 2

        fish_evaluated = super().update(instance, validated_data)

        mortality_delta = fish_evaluated.mortality_quantity - previous_mortality
        if mortality_delta > 0:
            self._apply_mortality_stock_change(
                cycle=fish_evaluated.cycle,
                pond=fish_evaluated.pond,
                quantity=mortality_delta,
                batch_id=batch_id,
            )
        elif mortality_delta < 0:
            self._apply_mortality_stock_change(
                cycle=fish_evaluated.cycle,
                pond=fish_evaluated.pond,
                quantity=abs(mortality_delta),
                batch_id=batch_id,
                restore=True,
            )

        self._refresh_cycle_control_stat(fish_evaluated, ignore_same_day=True)
        return fish_evaluated

    @transaction.atomic
    def create(self, validated_data):
        """
        Crea FishEvaluated calculando avg_weight_g automáticamente.

        avg_weight_g = (min_weight_g + max_weight_g) / 2
        """
        batch_id = validated_data.pop("batch_id", None)

        # Calcular avg_weight_g automáticamente
        min_weight = validated_data.get("min_weight_g", 0)
        max_weight = validated_data.get("max_weight_g", 0)
        validated_data["avg_weight_g"] = (min_weight + max_weight) / 2

        # Obtener cycle y pond desde validated_data
        # Si vienen como IDs, resolverlos
        if "cycle_id" in validated_data and "cycle" not in validated_data:
            cycle = Cycle.objects.get(id=validated_data.pop("cycle_id"))
            validated_data["cycle"] = cycle
        else:
            cycle = validated_data.get("cycle")

        if "pond_id" in validated_data and "pond" not in validated_data:
            pond = Pond.objects.get(id=validated_data.pop("pond_id"))
            validated_data["pond"] = pond
        else:
            pond = validated_data.get("pond")

        if cycle is not None and validated_data.get("farm") is None:
            validated_data["farm"] = cycle.farm
        elif pond is not None and validated_data.get("farm") is None:
            validated_data["farm"] = pond.farm

        mortality_quantity = validated_data.get("mortality_quantity", 0)

        # Crear la evaluación
        fish_evaluated = super().create(validated_data)

        if mortality_quantity > 0:
            self._apply_mortality_stock_change(
                cycle=cycle,
                pond=pond,
                quantity=mortality_quantity,
                batch_id=batch_id,
            )

        active_cycle_pond_batches = self._get_active_cycle_pond_batches(cycle, pond)
        all_dead = active_cycle_pond_batches and all(
            cpb.pond_batch.current_quantity <= 0 for cpb in active_cycle_pond_batches
        )

        if all_dead:
            # Si todos los batches del estanque están muertos, cancelar el ciclo
            cycle.state = Cycle.State.CANCELLED
            cycle.save(update_fields=["state"])

        self._refresh_cycle_control_stat(fish_evaluated, ignore_same_day=True)

        return fish_evaluated


class ProductUsageLogSerializer(serializers.ModelSerializer):
    """
    Serializer para registros de uso de productos.
    ProductUsageLog SOLO se crea EN CONJUNTO con DailyStat (como campo anidado).
    No se puede crear de forma independiente.
    """

    class Meta:
        model = ProductUsageLog
        fields = [
            "id",
            "daily_stat",
            "product",
            "quantity_used",
            "unit",
            "batch",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, data):
        daily_stat = data.get("daily_stat")
        product = data.get("product")
        batch = data.get("batch")
        quantity_used = data.get("quantity_used")

        # ProductUsageLog SIEMPRE debe estar ligado a un DailyStat
        # Se valida aquí para evitar creaciones independientes
        if not daily_stat:
            raise serializers.ValidationError(
                {
                    "daily_stat": "ProductUsageLog NO se crea independientemente. Crea product_usages EN CONJUNTO al crear DailyStat en la misma solicitud POST."
                }
            )

        # Validar cantidad > 0
        if quantity_used is not None and quantity_used <= 0:
            raise serializers.ValidationError(
                {"quantity_used": "La cantidad usada debe ser mayor a 0."}
            )

        # Validar que el producto pertenece a la misma farm
        if daily_stat and product:
            if product.farm_id != daily_stat.cycle.farm_id:
                raise serializers.ValidationError(
                    {
                        "product": "El producto debe pertenecer a la misma granja que el ciclo."
                    }
                )

        # Validar que el batch pertenece a la misma farm
        if daily_stat and batch:
            if batch.farm_id != daily_stat.cycle.farm_id:
                raise serializers.ValidationError(
                    {"batch": "El lote debe pertenecer a la misma granja que el ciclo."}
                )

        # Validar que el batch está ACTIVE
        if batch and batch.status != Batch.Status.ACTIVE:
            raise serializers.ValidationError(
                {"batch": "El lote debe estar en estado ACTIVE."}
            )

        return data


class DailyStatSerializer(serializers.ModelSerializer):
    """
    Serializer para estadísticas diarias con soporte para crear ProductUsageLog anidados.
    """

    product_usages = ProductUsageLogSerializer(
        many=True, write_only=True, required=False
    )

    class Meta:
        model = DailyStat
        fields = [
            "id",
            "cycle",
            "pond",
            "stat_date",
            "name",
            "description",
            "product_usages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["cycle", "pond", "created_at", "updated_at"]

    def validate(self, data):
        cycle = data.get("cycle") or (self.instance.cycle if self.instance else None)
        pond = data.get("pond") or (self.instance.pond if self.instance else None)
        stat_date = data.get("stat_date") or (
            self.instance.stat_date if self.instance else None
        )

        # Validar que el ciclo está IN_PROGRESS
        if cycle:
            if cycle.state != Cycle.State.IN_PROGRESS:
                raise serializers.ValidationError(
                    {"cycle": "El ciclo debe estar en estado IN_PROGRESS."}
                )

        # Validar que el estanque está IN_USE
        if pond:
            if pond.status != Pond.Status.IN_USE:
                raise serializers.ValidationError(
                    {"pond": "El estanque debe estar en estado IN_USE."}
                )

        # Validar que el estanque está asociado al ciclo
        if cycle and pond:
            cpb_exists = CyclePondBatch.objects.filter(
                cycle=cycle,
                pond_batch__pond=pond,
                pond_batch__end_date__isnull=True,
            ).exists()
            if not cpb_exists:
                raise serializers.ValidationError(
                    {"pond": "El estanque no está asociado a este ciclo."}
                )

        # Validar que la fecha <= hoy
        if stat_date and stat_date > date.today():
            raise serializers.ValidationError(
                {"stat_date": "La fecha del stat no puede ser futura."}
            )

        return data

    @transaction.atomic
    def create(self, validated_data):
        """
        Crea DailyStat con ProductUsageLogs anidados de forma ATÓMICA.

        Flujo:
        1. Crea el DailyStat
        2. Para cada product_usage:
           - Crea ProductUsageLog
           - Llama create_out_movement() para descontar del inventario
        3. Si algún paso falla, revierte TODO (incluyendo el DailyStat)

        El descuento de inventario se registra en InventoryMovement con tipo OUT.
        """
        product_usages_data = validated_data.pop("product_usages", [])

        # Crear el DailyStat
        daily_stat = DailyStat.objects.create(**validated_data)

        try:
            # Crear ProductUsageLogs y sus InventoryMovements
            for usage_data in product_usages_data:
                usage_data["daily_stat"] = daily_stat
                product_usage = ProductUsageLog.objects.create(**usage_data)

                # Crear InventoryMovement OUT (descontar del inventario)
                # Si hay error de stock, create_out_movement() lanza ValueError
                # y la transacción se revierte completamente
                create_out_movement(
                    farm=daily_stat.cycle.farm,
                    product=product_usage.product,
                    quantity=product_usage.quantity_used,
                    source_type=InventoryMovement.SourceType.DAILY,
                    source_id=product_usage.id,
                    observations=f"Uso registrado en Daily Stat {daily_stat.id}",
                    pond=daily_stat.pond,
                    cycle=daily_stat.cycle,
                )
        except ValueError as e:
            # ValueError se lanza si no hay stock suficiente
            # La transacción @transaction.atomic revierte automáticamente
            raise serializers.ValidationError({"product_usages": str(e)})

        return daily_stat


class ControlStatSerializer(serializers.ModelSerializer):
    """
    Serializer para estadísticas de control (READ-ONLY).

    ControlStat se genera AUTOMÁTICAMENTE cada vez que se crea un FishEvaluated.
    El frontend NO crea ControlStat manualmente.

    control_date es read-only y se asigna como evaluation_date del FishEvaluated.
    """

    class Meta:
        model = ControlStat
        fields = [
            "id",
            "cycle",
            "pond",
            "control_date",
            "sampled_quantity",
            "live_quantity",
            "min_weight_g",
            "avg_weight_g",
            "max_weight_g",
            "mortality_percentage",
            "biomass_kg",
            "fca",
            "biomass_gain_kg",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "cycle",
            "pond",
            "control_date",
            "sampled_quantity",
            "live_quantity",
            "min_weight_g",
            "avg_weight_g",
            "max_weight_g",
            "mortality_percentage",
            "biomass_kg",
            "fca",
            "biomass_gain_kg",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        cycle = data.get("cycle") or (self.instance.cycle if self.instance else None)
        pond = data.get("pond") or (self.instance.pond if self.instance else None)
        control_date = data.get("control_date") or (
            self.instance.control_date if self.instance else None
        )

        # Validar que el ciclo está IN_PROGRESS
        if cycle:
            if cycle.state != Cycle.State.IN_PROGRESS:
                raise serializers.ValidationError(
                    {"cycle": "El ciclo debe estar en estado IN_PROGRESS."}
                )

        # Validar que el estanque está IN_USE
        if pond:
            if pond.status != Pond.Status.IN_USE:
                raise serializers.ValidationError(
                    {"pond": "El estanque debe estar en estado IN_USE."}
                )

        # Validar que el estanque está asociado al ciclo
        if cycle and pond:
            cpb_exists = CyclePondBatch.objects.filter(
                cycle=cycle,
                pond_batch__pond=pond,
                pond_batch__end_date__isnull=True,
            ).exists()
            if not cpb_exists:
                raise serializers.ValidationError(
                    {"pond": "El estanque no está asociado a este ciclo."}
                )

        # Validar que debe existir al menos 1 FishEvaluated previo
        if cycle and pond and control_date:
            fish_evals = FishEvaluated.objects.filter(
                cycle=cycle,
                pond=pond,
                evaluation_date__lte=control_date,
                deleted_at__isnull=True,
            )
            if not fish_evals.exists():
                raise serializers.ValidationError(
                    {
                        "control_date": "Debe existir al menos una evaluación de peces previa a la fecha de control."
                    }
                )

        # Validar que control_date <= hoy
        if control_date and control_date > date.today():
            raise serializers.ValidationError(
                {"control_date": "La fecha del control no puede ser futura."}
            )

        return data

    def create(self, validated_data):
        cycle = validated_data["cycle"]
        pond = validated_data["pond"]
        control_date = validated_data["control_date"]

        # Obtener todas las evaluaciones hasta la fecha de control
        evaluations = FishEvaluated.objects.filter(
            cycle=cycle,
            pond=pond,
            evaluation_date__lte=control_date,
            deleted_at__isnull=True,
        )

        # Calcular estadísticas agregadas
        stats = FishEvaluatedCalculator.aggregate_fish_evaluations(evaluations)

        sample_live_quantity = stats["live_quantity"]
        live_quantity, current_biomass = BiomassCalculator.calculate_control_biomass(
            cycle.id,
            pond.id,
            stats["avg_weight_g"],
            mortality_quantity=stats["sampled_quantity"] - sample_live_quantity,
            fallback_live_quantity=sample_live_quantity,
        )

        previous_control = BiomassCalculator.get_previous_control_stat(
            cycle.id, pond.id, control_date
        )

        biomass_gain = None
        fca = None

        if previous_control is not None:
            biomass_gain = BiomassCalculator.calculate_biomass_gain(
                current_biomass, previous_control.biomass_kg
            )
            from apps.feeding.utils import cycle_feed_consumed_kg

            alimento_kg = cycle_feed_consumed_kg(
                cycle_id=cycle.id,
                start_date=previous_control.control_date,
                end_date=control_date,
            )
            fca = BiomassCalculator.calculate_fca(float(alimento_kg), biomass_gain)

        # Crear el ControlStat con los datos calculados
        control_stat = ControlStat.objects.create(
            cycle=cycle,
            pond=pond,
            control_date=control_date,
            sampled_quantity=stats["sampled_quantity"],
            live_quantity=live_quantity,
            min_weight_g=stats["min_weight_g"],
            avg_weight_g=stats["avg_weight_g"],
            max_weight_g=stats["max_weight_g"],
            mortality_percentage=stats["mortality_percentage"],
            biomass_kg=current_biomass,
            fca=fca,
            biomass_gain_kg=biomass_gain,
        )

        return control_stat


__all__ = [
    "FishEvaluatedSerializer",
    "DailyStatSerializer",
    "ProductUsageLogSerializer",
    "ControlStatSerializer",
]
