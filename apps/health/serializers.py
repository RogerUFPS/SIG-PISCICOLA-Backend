from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.monitoring.serializers import FishEvaluatedSerializer
from apps.products.models import Product

from .constants import (FISH_EVALUATION_CREATE_FIELDS,
                        TREATMENT_PLAN_DATE_OVERLAP_MESSAGE)
from .models import HealthStat, TreatmentEvent, TreatmentPlan
from .utils import (active_treatment_plan_date_overlap,
                    clear_treatment_inventory_for_event,
                    collect_combined_health_stat_payload_errors,
                    collect_disease_name_errors,
                    collect_health_stat_scope_errors,
                    collect_health_stat_update_errors,
                    collect_prior_fish_evaluation_errors,
                    collect_treatment_event_close_errors,
                    collect_treatment_plan_business_errors, create_health_stat,
                    create_health_stat_with_fish_evaluation,
                    create_treatment_events_for_plan,
                    pop_fish_evaluation_fields,
                    sync_treatment_inventory_for_event,
                    sync_treatment_plan_status, treatment_plan_lifecycle_state,
                    validate_fish_evaluation_with_monitoring)


class HealthStatSerializer(serializers.ModelSerializer):
    """Lectura de registros de salud (listado, detalle)."""

    class Meta:
        model = HealthStat
        fields = [
            "id",
            "farm",
            "cycle",
            "pond",
            "date",
            "disease_name",
            "severity_level",
            "comments",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class _HealthStatWriteSerializer(serializers.ModelSerializer):
    """Campos comunes para crear un HealthStat."""

    class Meta:
        model = HealthStat
        fields = [
            "farm",
            "cycle",
            "pond",
            "date",
            "disease_name",
            "severity_level",
            "comments",
        ]

    def _scope_entities(self, data):
        farm = data.get("farm") or (self.instance.farm if self.instance else None)
        cycle = data.get("cycle") or (self.instance.cycle if self.instance else None)
        pond = data.get("pond") or (self.instance.pond if self.instance else None)
        stat_date = data.get("date") or (self.instance.date if self.instance else None)
        return farm, cycle, pond, stat_date

    def _collect_scope_errors(self, data) -> dict:
        farm, cycle, pond, stat_date = self._scope_entities(data)
        if farm and cycle and pond and stat_date is not None:
            return collect_health_stat_scope_errors(
                farm=farm, cycle=cycle, pond=pond, stat_date=stat_date
            )
        return {}


class HealthStatCreateSerializer(_HealthStatWriteSerializer):
    """
    POST solo salud: requiere evaluación de peces previa en el ciclo/estanque.
    """

    def validate(self, data):
        errors = self._collect_scope_errors(data)
        farm, cycle, pond, stat_date = self._scope_entities(data)

        if cycle and pond and stat_date is not None:
            errors.update(
                collect_prior_fish_evaluation_errors(
                    cycle=cycle, pond=pond, stat_date=stat_date
                )
            )
        errors.update(collect_disease_name_errors(data.get("disease_name")))

        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        return create_health_stat(
            validated_data=validated_data,
            created_by=self.context["request"].user,
        )


class HealthStatWithFishEvaluationCreateSerializer(_HealthStatWriteSerializer):
    """
    POST combinado: registro de salud + evaluación de peces en un solo formulario.
    ``date`` aplica a ambos.
    """

    sampled_quantity = serializers.IntegerField(min_value=1, write_only=True)
    mortality_quantity = serializers.IntegerField(
        min_value=0, required=False, write_only=True, default=0
    )
    min_weight_g = serializers.FloatField(min_value=0, write_only=True)
    max_weight_g = serializers.FloatField(min_value=0, write_only=True)
    observations = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, write_only=True
    )
    batch_id = serializers.IntegerField(required=False, write_only=True)

    class Meta(_HealthStatWriteSerializer.Meta):
        fields = _HealthStatWriteSerializer.Meta.fields + [
            "sampled_quantity",
            "mortality_quantity",
            "min_weight_g",
            "max_weight_g",
            "observations",
            "batch_id",
        ]

    def validate(self, data):
        errors = self._collect_scope_errors(data)
        farm, cycle, pond, stat_date = self._scope_entities(data)

        fish = {key: data[key] for key in FISH_EVALUATION_CREATE_FIELDS if key in data}
        eval_context = dict(self.context)
        if farm is not None:
            eval_context["farm"] = farm

        min_w = data.get("min_weight_g")
        max_w = data.get("max_weight_g")
        if min_w is not None and max_w is not None and min_w > max_w:
            errors["min_weight_g"] = (
                "El peso mínimo no puede ser mayor que el peso máximo."
            )

        if cycle and pond and stat_date is not None:
            errors.update(
                validate_fish_evaluation_with_monitoring(
                    cycle=cycle,
                    pond=pond,
                    stat_date=stat_date,
                    fish=fish,
                    serializer_context=eval_context,
                )
            )
            errors.update(
                collect_combined_health_stat_payload_errors(
                    cycle=cycle,
                    pond=pond,
                    stat_date=stat_date,
                    disease_name=data.get("disease_name"),
                    fish=fish,
                )
            )
        errors.update(collect_disease_name_errors(data.get("disease_name")))

        if errors:
            raise serializers.ValidationError(errors)
        return data

    def create(self, validated_data):
        validated_data, fish = pop_fish_evaluation_fields(validated_data)
        try:
            result = create_health_stat_with_fish_evaluation(
                validated_data=validated_data,
                fish=fish,
                created_by=self.context["request"].user,
                serializer_context=self.context,
            )
        except ValueError as exc:
            if exc.args and isinstance(exc.args[0], dict):
                raise serializers.ValidationError(exc.args[0]) from exc
            raise
        self.context["_combined_create"] = result
        return result["health_stat"]

    def to_representation(self, instance):
        combined = self.context.get("_combined_create")
        if combined and combined.get("health_stat").pk == instance.pk:
            return {
                "health_stat": HealthStatSerializer(
                    instance,
                    context=self.context,
                ).data,
                "fish_evaluation": FishEvaluatedSerializer(
                    combined["fish_evaluation"],
                    context=self.context,
                ).data,
            }
        return HealthStatSerializer(instance, context=self.context).data


class HealthStatUpdateSerializer(serializers.ModelSerializer):
    """PATCH parcial: disease_name, severity_level, comments; date solo sin planes."""

    class Meta:
        model = HealthStat
        fields = ["disease_name", "severity_level", "comments", "date"]

    def validate(self, data):
        if not data:
            raise serializers.ValidationError(
                "Envíe al menos un campo para actualizar."
            )
        errors = collect_health_stat_update_errors(
            health_stat=self.instance,
            data=data,
        )
        if errors:
            raise serializers.ValidationError(errors)
        return data


class TreatmentPlanSerializer(serializers.ModelSerializer):
    """
    Plan de tratamiento. En PATCH use ``context={"replace_plan": plan, "farm_id": ...}``
    para reemplazar un plan programado o en curso (misma lógica que feeding).
    """

    class Meta:
        model = TreatmentPlan
        fields = [
            "id",
            "farm",
            "health_stat",
            "product",
            "start_date",
            "end_date",
            "dose_per_application",
            "unit",
            "times_per_day",
            "gap_between_times_per_day",
            "gap_between_completed_day",
            "application_method",
            "reason",
            "notes",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["farm", "status", "created_by", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Unit

        self.fields["unit"].queryset = Unit.objects.all()
        self.fields["product"].queryset = Product.objects.filter(
            deleted_at__isnull=True
        )

    def validate(self, data):
        if self.context.get("replace_plan"):
            return self._validate_replace(data)
        if self.instance is not None:
            raise serializers.ValidationError(
                "Para modificar un plan use PATCH con contexto replace_plan."
            )
        return self._validate_create(data)

    def _validate_create(self, data):
        farm = self.context.get("farm")
        farm_id = getattr(farm, "pk", farm) if farm is not None else None
        if farm_id is None:
            raise serializers.ValidationError(
                {"farm": "Contexto de granja requerido para crear el plan."}
            )

        health_stat = self._resolve_health_stat(
            data["health_stat"],
            farm_id,
            fixed_health_stat_id=self.context.get("fixed_health_stat_id"),
        )
        self._validate_plan_fields(
            farm_id=farm_id,
            health_stat=health_stat,
            data=data,
            exclude_plan_ids=None,
        )
        return data

    def _validate_replace(self, data):
        old: TreatmentPlan = self.context["replace_plan"]
        farm_id = self.context["farm_id"]

        if treatment_plan_lifecycle_state(old) == "finished":
            raise serializers.ValidationError(
                "No se puede modificar un plan cuya fecha de fin ya pasó."
            )
        if old.status == TreatmentPlan.Status.CANCELLED:
            raise serializers.ValidationError(
                "No se puede modificar un plan cancelado."
            )

        health_stat = self._resolve_health_stat(
            data["health_stat"],
            farm_id,
            fixed_health_stat_id=self.context.get("fixed_health_stat_id"),
        )

        self._validate_plan_fields(
            farm_id=farm_id,
            health_stat=health_stat,
            data=data,
            exclude_plan_ids={old.pk},
        )

        if treatment_plan_lifecycle_state(old) == "in_progress":
            last_ev = (
                TreatmentEvent.objects.filter(
                    treatment_plan_id=old.pk,
                    status__in=(
                        TreatmentEvent.Status.COMPLETED,
                        TreatmentEvent.Status.SKIPPED,
                    ),
                )
                .order_by("-date", "-scheduled_time", "-application_number")
                .first()
            )
            if last_ev is None:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Para actualizar un plan en curso debe existir al menos un "
                            "evento marcado como completado u omitido."
                        ]
                    }
                )
            if data["start_date"] <= last_ev.date:
                raise serializers.ValidationError(
                    {
                        "start_date": (
                            "La fecha de inicio del nuevo plan debe ser posterior al día "
                            "del último evento completado u omitido."
                        )
                    }
                )

        return data

    @staticmethod
    def _resolve_plan_product(product):
        if product is None:
            return None
        product_pk = getattr(product, "pk", product)
        return (
            Product.objects.select_related("type_product").filter(pk=product_pk).first()
        )

    def _resolve_health_stat(self, health_stat, farm_id, fixed_health_stat_id=None):
        health_stat_pk = getattr(health_stat, "pk", health_stat)
        try:
            hs = HealthStat.objects.select_related("cycle", "pond", "farm").get(
                pk=health_stat_pk
            )
        except HealthStat.DoesNotExist:
            raise serializers.ValidationError(
                {"health_stat": "Registro de salud no encontrado."}
            ) from None
        if fixed_health_stat_id is not None and hs.pk != fixed_health_stat_id:
            raise serializers.ValidationError(
                {"health_stat": ("El registro de salud no coincide con el de la URL.")}
            )
        if hs.farm_id != farm_id:
            raise serializers.ValidationError(
                {"health_stat": "El registro de salud debe pertenecer a la granja."}
            )
        return hs

    def _validate_plan_fields(
        self,
        *,
        farm_id,
        health_stat,
        data,
        exclude_plan_ids,
    ):
        product = self._resolve_plan_product(data.get("product"))
        plan_errors = collect_treatment_plan_business_errors(
            farm_id=farm_id,
            health_stat=health_stat,
            product=product,
            start_date=data["start_date"],
            end_date=data["end_date"],
            times_per_day=data["times_per_day"],
            gap_between_times_per_day=data["gap_between_times_per_day"],
            gap_between_completed_day=data["gap_between_completed_day"],
            dose_per_application=data["dose_per_application"],
        )
        if plan_errors:
            raise serializers.ValidationError(plan_errors)

        if active_treatment_plan_date_overlap(
            health_stat_id=health_stat.pk,
            start_date=data["start_date"],
            end_date=data["end_date"],
            exclude_plan_ids=exclude_plan_ids,
        ):
            raise serializers.ValidationError(
                {
                    "start_date": TREATMENT_PLAN_DATE_OVERLAP_MESSAGE,
                    "end_date": TREATMENT_PLAN_DATE_OVERLAP_MESSAGE,
                }
            )

    def create(self, validated_data):
        validated_data["farm"] = self.context["farm"]
        health_stat = validated_data["health_stat"]
        user = self.context["request"].user
        with transaction.atomic():
            if active_treatment_plan_date_overlap(
                health_stat_id=health_stat.pk,
                start_date=validated_data["start_date"],
                end_date=validated_data["end_date"],
            ):
                raise serializers.ValidationError(
                    {
                        "start_date": TREATMENT_PLAN_DATE_OVERLAP_MESSAGE,
                        "end_date": TREATMENT_PLAN_DATE_OVERLAP_MESSAGE,
                    }
                )
            plan = TreatmentPlan.objects.create(
                **validated_data,
                created_by=user,
                status=TreatmentPlan.Status.SCHEDULED,
            )
            create_treatment_events_for_plan(plan)
        return plan


class TreatmentEventSerializer(serializers.ModelSerializer):
    """
    Aplicación de tratamiento. En PATCH (``partial=True``) solo se pueden editar
    ``status``, ``actual_dose``, ``actual_unit`` y ``notes``.
    """

    PATCH_WRITABLE = frozenset({"status", "actual_dose", "actual_unit", "notes"})

    class Meta:
        model = TreatmentEvent
        fields = [
            "id",
            "farm",
            "cycle",
            "treatment_plan",
            "date",
            "scheduled_time",
            "application_number",
            "planned_dose",
            "planned_unit",
            "status",
            "completed_at",
            "actual_dose",
            "actual_unit",
            "notes",
            "completed_by",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is None:
            return
        if self.partial:
            for name, field in self.fields.items():
                field.read_only = name not in self.PATCH_WRITABLE
        else:
            for field in self.fields.values():
                field.read_only = True

    def validate_actual_dose(self, value):
        initial = getattr(self, "initial_data", {}) or {}
        if self.partial:
            if initial.get("status") == TreatmentEvent.Status.SKIPPED:
                return value
            if "actual_dose" not in initial:
                return value
        if value is None:
            raise serializers.ValidationError(
                "La dosis real es obligatoria y debe ser mayor a cero."
            )
        if value <= 0:
            raise serializers.ValidationError("La dosis real debe ser mayor a cero.")
        return value

    def validate(self, data):
        if not self.partial or self.instance is None:
            return data
        return self._validate_patch(data)

    def _validate_patch(self, data):
        instance = self.instance

        if instance.status == TreatmentEvent.Status.SKIPPED:
            raise serializers.ValidationError(
                "No se puede modificar un evento omitido."
            )

        if instance.status == TreatmentEvent.Status.COMPLETED:
            if "status" in data:
                if data["status"] == TreatmentEvent.Status.SKIPPED:
                    extra = set(data) - {"status"}
                    if extra:
                        raise serializers.ValidationError(
                            {
                                "status": (
                                    "Para omitir un evento completado envíe solo "
                                    "status=skipped (se devolverá el inventario descontado)."
                                )
                            }
                        )
                    return data
                raise serializers.ValidationError(
                    {
                        "status": (
                            "No puede cambiar el estado de un evento ya completado; use "
                            "status=skipped para revertir o corrija dosis, unidad o notas."
                        )
                    }
                )
            if not data:
                raise serializers.ValidationError(
                    "Envíe actual_dose, actual_unit y/o notes para corregir el registro."
                )
            if instance.treatment_plan.product_id and (
                "actual_dose" in data or "actual_unit" in data
            ):
                dose = data.get("actual_dose", instance.actual_dose)
                unit = data.get("actual_unit", instance.actual_unit)
                if dose is None or unit is None:
                    raise serializers.ValidationError(
                        {
                            "actual_dose": (
                                "Al corregir el consumo, indique dosis y unidad."
                            )
                        }
                    )
            return data

        # scheduled — mismo orden que FeedingEventUpdateSerializer: primero status.
        if data.get("status") == TreatmentEvent.Status.SKIPPED:
            data.pop("actual_dose", None)
            data.pop("actual_unit", None)

        if "status" not in data:
            if "actual_dose" in data or "actual_unit" in data:
                raise serializers.ValidationError(
                    {
                        "status": (
                            "Mientras el evento está programado no se aceptan dosis ni unidad "
                            "reales sin cerrar el evento. Envíe status=completed con "
                            "actual_dose y actual_unit, o status=skipped."
                        )
                    }
                )
            if "notes" in data:
                return data
            raise serializers.ValidationError(
                {
                    "status": (
                        "Indique status=completed o status=skipped para cerrar el evento."
                    )
                }
            )

        new_status = data["status"]
        if new_status not in (
            TreatmentEvent.Status.COMPLETED,
            TreatmentEvent.Status.SKIPPED,
        ):
            raise serializers.ValidationError(
                {
                    "status": (
                        "Cuando envía «status», solo se aceptan «completed» o «skipped»."
                    )
                }
            )

        if new_status == TreatmentEvent.Status.COMPLETED:
            if "actual_dose" not in data:
                raise serializers.ValidationError(
                    {"actual_dose": ("Indique la dosis real al completar el evento.")}
                )
            if "actual_unit" not in data:
                raise serializers.ValidationError(
                    {
                        "actual_unit": (
                            "Indique la unidad de la dosis real al completar el evento."
                        )
                    }
                )
        elif "actual_dose" in data or "actual_unit" in data:
            raise serializers.ValidationError(
                {
                    "status": (
                        "Para omitir el evento envíe solo status=skipped, sin dosis ni "
                        "unidad real."
                    )
                }
            )

        close_errors = collect_treatment_event_close_errors(instance)
        if close_errors:
            raise serializers.ValidationError(close_errors)

        return data

    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = (
            request.user
            if request and getattr(request.user, "is_authenticated", False)
            else None
        )

        if instance.status == TreatmentEvent.Status.COMPLETED:
            if validated_data.get("status") == TreatmentEvent.Status.SKIPPED:
                with transaction.atomic():
                    clear_treatment_inventory_for_event(instance.pk)
                    instance.status = TreatmentEvent.Status.SKIPPED
                    instance.actual_dose = None
                    instance.actual_unit = None
                    instance.completed_at = timezone.now()
                    if user is not None:
                        instance.completed_by = user
                    instance.save()
                sync_treatment_plan_status(instance.treatment_plan)
                return instance

            with transaction.atomic():
                if "actual_dose" in validated_data:
                    instance.actual_dose = validated_data["actual_dose"]
                if "actual_unit" in validated_data:
                    instance.actual_unit = validated_data["actual_unit"]
                if "notes" in validated_data:
                    instance.notes = validated_data["notes"]
                if instance.treatment_plan.product_id and (
                    "actual_dose" in validated_data or "actual_unit" in validated_data
                ):
                    try:
                        sync_treatment_inventory_for_event(instance)
                    except ValueError as exc:
                        raise serializers.ValidationError({"detail": str(exc)}) from exc
                instance.save()
            return instance

        new_status = validated_data["status"]

        if new_status == TreatmentEvent.Status.COMPLETED:
            with transaction.atomic():
                instance.actual_dose = validated_data["actual_dose"]
                instance.actual_unit = validated_data["actual_unit"]
                if "notes" in validated_data:
                    instance.notes = validated_data["notes"]
                if instance.treatment_plan.product_id:
                    try:
                        sync_treatment_inventory_for_event(instance)
                    except ValueError as exc:
                        raise serializers.ValidationError({"detail": str(exc)}) from exc

                instance.status = new_status
                instance.completed_at = timezone.now()
                if user is not None:
                    instance.completed_by = user
                instance.save()
            sync_treatment_plan_status(instance.treatment_plan)
            return instance

        with transaction.atomic():
            if "notes" in validated_data:
                instance.notes = validated_data["notes"]
            clear_treatment_inventory_for_event(instance.pk)
            instance.status = new_status
            instance.completed_at = timezone.now()
            if user is not None:
                instance.completed_by = user
            instance.save()

        sync_treatment_plan_status(instance.treatment_plan)
        return instance


__all__ = [
    "HealthStatSerializer",
    "HealthStatCreateSerializer",
    "HealthStatWithFishEvaluationCreateSerializer",
    "HealthStatUpdateSerializer",
    "TreatmentPlanSerializer",
    "TreatmentEventSerializer",
]
