from decimal import Decimal
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.cycle.models import Cycle
from apps.products.models import Product
from apps.species.models import Specie, SpecieFeedingReference

from .constants import (FEED_SCHEDULE_PRODUCT_TYPE_NAMES,
                        FEEDING_PLAN_DATE_OVERLAP_MESSAGE,
                        FEEDING_SCHEDULE_CREATE_PARENT_MESSAGE,
                        FEEDING_SCHEDULE_PATCH_FORBIDDEN_MESSAGES,
                        FEEDING_SCHEDULE_REFERENCE_DEFAULT_FIELDS,
                        FEEDING_SCHEDULE_REFERENCE_WEIGHT_FIELDS,
                        FEEDING_SCHEDULE_SYSTEM_ASSIGNED_FIELDS,
                        FEEDING_SCHEDULE_SYSTEM_ASSIGNED_MESSAGE,
                        FEEDING_SCHEDULE_VERSION_MERGE_FIELDS, MINUTES_PER_DAY)
from .models import FeedingEvent, FeedingPlan, FeedingSchedule
from .utils import (active_plan_date_overlap,
                    clear_feeding_inventory_for_event,
                    collect_feeding_plan_business_errors,
                    create_feeding_events_for_plan,
                    feeding_plan_lifecycle_state,
                    sync_feeding_inventory_for_event)


class FeedingScheduleSerializer(serializers.ModelSerializer):
    warnings = serializers.SerializerMethodField(read_only=True)
    recommendations = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = FeedingSchedule
        fields = [
            "id",
            "farm",
            "product",
            "specie",
            "name",
            "comments",
            "type",
            "aceptable_min_weight_g",
            "aceptable_max_weight_g",
            "feed_form",
            "pellet_size_mm",
            "feeding_rate_percentage",
            "times_per_day",
            "gap_between_times_per_day",
            "gap_between_completed_day",
            "expected_fca",
            "expected_daily_gain_g",
            "version",
            "is_current",
            "parent",
            "created_at",
            "updated_at",
            "deleted_at",
            "warnings",
            "recommendations",
        ]
        read_only_fields = [
            "farm",
            "created_at",
            "updated_at",
            "deleted_at",
            "warnings",
            "recommendations",
        ]

        extra_kwargs = {
            field: {"required": False, "allow_null": True}
            for field in (
                *FEEDING_SCHEDULE_REFERENCE_DEFAULT_FIELDS,
                *FEEDING_SCHEDULE_REFERENCE_WEIGHT_FIELDS,
            )
        }

    def validate_name(self, value):
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError(
                "El nombre no puede estar vacío ni ser solo espacios."
            )
        return text

    def validate_aceptable_min_weight_g(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "El peso mínimo aceptable debe ser mayor a 0."
            )
        return value

    def validate_aceptable_max_weight_g(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "El peso máximo aceptable debe ser mayor a 0."
            )
        return value

    def validate_feeding_rate_percentage(self, value):
        if not (0 < value <= 100):
            raise serializers.ValidationError(
                "El porcentaje de alimentación debe ser mayor a 0 y como máximo 100."
            )
        return value

    def validate_pellet_size_mm(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "El tamaño del pellet debe ser mayor a 0."
            )
        return value

    def validate_times_per_day(self, value):
        if value < 1:
            raise serializers.ValidationError("Las veces por día deben ser al menos 1.")
        return value

    def validate_gap_between_times_per_day(self, value):
        if value < 1:
            raise serializers.ValidationError(
                "El intervalo entre raciones debe ser de al menos 1 minuto."
            )
        return value

    def validate_gap_between_completed_day(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "El intervalo entre jornadas no puede ser negativo. Use 0 para alimentar todos los días."
            )
        return value

    def validate_expected_fca(self, value):
        if value <= 0:
            raise serializers.ValidationError("El FCA esperado debe ser mayor a 0.")
        return value

    def validate_expected_daily_gain_g(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "La ganancia diaria esperada debe ser mayor a 0."
            )
        return value

    def validate(self, data):
        instance = self.instance
        farm_ctx = self.context.get("farm")
        if instance is None and farm_ctx is not None:
            if getattr(farm_ctx, "deleted_at", None) is not None:
                raise serializers.ValidationError(
                    {
                        "farm": (
                            "Solo puede crear cronogramas para una granja activa "
                            "(sin baja lógica)."
                        ),
                    }
                )
        if instance is not None:
            for field, message in FEEDING_SCHEDULE_PATCH_FORBIDDEN_MESSAGES.items():
                if field in data:
                    raise serializers.ValidationError({field: message})
        if instance is None and data.get("parent") is not None:
            raise serializers.ValidationError(
                {"parent": FEEDING_SCHEDULE_CREATE_PARENT_MESSAGE}
            )
        if instance is None:
            for field in FEEDING_SCHEDULE_SYSTEM_ASSIGNED_FIELDS:
                if field in data:
                    raise serializers.ValidationError(
                        {field: FEEDING_SCHEDULE_SYSTEM_ASSIGNED_MESSAGE}
                    )
        times_pd = data.get(
            "times_per_day",
            getattr(instance, "times_per_day", None),
        )
        gap_min = data.get(
            "gap_between_times_per_day",
            getattr(instance, "gap_between_times_per_day", None),
        )
        if times_pd is not None and gap_min is not None and times_pd > 1:
            total_span = (times_pd - 1) * gap_min
            if total_span >= MINUTES_PER_DAY:
                max_gap = (MINUTES_PER_DAY - 1) // (times_pd - 1)
                raise serializers.ValidationError(
                    {
                        "gap_between_times_per_day": (
                            f"Con {times_pd} raciones por día no caben intervalos de "
                            f"{gap_min} minutos entre raciones consecutivas: de la primera a la "
                            f"última suman {total_span} minutos y deben caber en un día "
                            f"(menos de {MINUTES_PER_DAY}). Con esa frecuencia el intervalo "
                            f"máximo es {max_gap} minutos."
                        )
                    }
                )

        farm = self.context.get("farm")
        farm_id = getattr(farm, "pk", farm) if farm is not None else None
        if farm_id is None and instance is not None:
            farm_id = instance.farm_id

        raw_product = data.get("product", getattr(instance, "product_id", None))
        product_id = getattr(raw_product, "pk", raw_product)

        if farm_id is not None and product_id is not None:
            try:
                product = Product.objects.select_related("type_product").get(
                    pk=product_id
                )
            except Product.DoesNotExist:
                raise serializers.ValidationError(
                    {"product": "Producto no encontrado."}
                )
            if product.deleted_at:
                raise serializers.ValidationError(
                    {"product": "El producto no está disponible."}
                )
            if product.farm_id != farm_id:
                raise serializers.ValidationError(
                    {
                        "product": (
                            "El producto debe pertenecer a la misma granja del cronograma."
                        )
                    }
                )
            tname = (product.type_product.name or "").casefold()
            if not any(tname == a.casefold() for a in FEED_SCHEDULE_PRODUCT_TYPE_NAMES):
                raise serializers.ValidationError(
                    {
                        "product": (
                            "El tipo de producto debe ser de alimentación permitida "
                            "para cronogramas."
                        ),
                    }
                )

        raw_specie = data.get("specie", getattr(instance, "specie_id", None))
        specie_pk = getattr(raw_specie, "pk", raw_specie)
        if farm_id is not None and specie_pk is not None:
            try:
                Specie.objects.get(pk=specie_pk)
            except Specie.DoesNotExist:
                raise serializers.ValidationError({"specie": "Especie no encontrada."})

        if farm_id is not None:
            if instance is None:
                schedule_name = data.get("name")
                if schedule_name is not None and data.get("parent") is None:
                    if FeedingSchedule.objects.filter(
                        farm_id=farm_id,
                        name__iexact=str(schedule_name),
                        is_current=True,
                    ).exists():
                        raise serializers.ValidationError(
                            {
                                "name": (
                                    "Ya existe un cronograma vigente con este nombre "
                                    "en la granja."
                                ),
                            }
                        )

        self._validate_acceptable_weight_pair(data)

        if instance is None:
            self._apply_reference_defaults_on_create(data, specie_pk)

        self._validate_weight_range(data, instance)
        self._enforce_warnings_confirmation(data, instance, specie_pk)

        return data

    @staticmethod
    def _field_sent(data, field: str) -> bool:
        return field in data

    def _validate_acceptable_weight_pair(self, data):
        min_key = "aceptable_min_weight_g"
        max_key = "aceptable_max_weight_g"
        min_sent = self._field_sent(data, min_key)
        max_sent = self._field_sent(data, max_key)
        if not min_sent and not max_sent:
            return
        if min_sent != max_sent:
            if not min_sent:
                raise serializers.ValidationError(
                    {
                        min_key: (
                            "Debe indicar el peso mínimo y el máximo aceptables juntos."
                        )
                    }
                )
            raise serializers.ValidationError(
                {
                    max_key: (
                        "Debe indicar el peso máximo y el mínimo aceptables juntos."
                    )
                }
            )

    def _validate_weight_range(self, data, instance):
        min_w = data.get(
            "aceptable_min_weight_g",
            getattr(instance, "aceptable_min_weight_g", None),
        )
        max_w = data.get(
            "aceptable_max_weight_g",
            getattr(instance, "aceptable_max_weight_g", None),
        )
        if min_w is not None and max_w is not None and min_w > max_w:
            raise serializers.ValidationError(
                {
                    "aceptable_min_weight_g": (
                        "El peso mínimo no puede ser mayor que el máximo."
                    )
                }
            )

    def _merged_version_value(self, data, instance, field):
        if instance is None:
            return data.get(field)
        if field in data:
            return data[field]
        return getattr(instance, field)

    def _schedule_snapshot_for_warnings(self, data, instance, specie_pk):
        if instance is None:
            specie_id = specie_pk
            getter = lambda field: data.get(field)
        else:
            specie_id = instance.specie_id
            getter = lambda field: self._merged_version_value(data, instance, field)

        return SimpleNamespace(
            specie_id=specie_id,
            type=getter("type"),
            feed_form=getter("feed_form"),
            expected_fca=getter("expected_fca"),
            expected_daily_gain_g=getter("expected_daily_gain_g"),
            aceptable_min_weight_g=getter("aceptable_min_weight_g"),
            aceptable_max_weight_g=getter("aceptable_max_weight_g"),
        )

    def _enforce_warnings_confirmation(self, data, instance, specie_pk):
        if self.context.get("confirm_warnings"):
            return
        snapshot = self._schedule_snapshot_for_warnings(data, instance, specie_pk)
        warnings = self.reference_warnings(snapshot)
        if not warnings:
            return
        raise serializers.ValidationError(
            {
                "requires_confirmation": True,
                "message": (
                    "Hay advertencias respecto a la referencia técnica. "
                    "Revíselas y reenvíe la solicitud con el parámetro "
                    "confirm_warnings=true si desea guardar de todos modos."
                ),
                "warnings": warnings,
            }
        )

    def _apply_recs_to_fields(self, data, recs, fields):
        for field in fields:
            if data.get(field) is not None:
                continue
            value = recs.get(field)
            if value is None:
                continue
            validator = getattr(self, f"validate_{field}", None)
            data[field] = validator(value) if validator else value

    @classmethod
    def _missing_reference_defaults(cls, data) -> list[str]:
        missing = [
            field
            for field in FEEDING_SCHEDULE_REFERENCE_DEFAULT_FIELDS
            if data.get(field) is None
        ]
        if all(
            data.get(field) is None
            for field in FEEDING_SCHEDULE_REFERENCE_WEIGHT_FIELDS
        ):
            missing.extend(FEEDING_SCHEDULE_REFERENCE_WEIGHT_FIELDS)
        return missing

    def _apply_reference_defaults_on_create(self, data, specie_pk):
        recs = self.reference_recommendations(
            specie_pk,
            data["type"],
            data["feed_form"],
        )
        self._apply_recs_to_fields(
            data, recs, FEEDING_SCHEDULE_REFERENCE_DEFAULT_FIELDS
        )
        if all(
            data.get(field) is None
            for field in FEEDING_SCHEDULE_REFERENCE_WEIGHT_FIELDS
        ):
            self._apply_recs_to_fields(
                data, recs, FEEDING_SCHEDULE_REFERENCE_WEIGHT_FIELDS
            )

        missing = self._missing_reference_defaults(data)
        if not missing:
            return

        if not recs:
            raise serializers.ValidationError(
                {
                    field: (
                        "Indique este valor o registre una referencia técnica para "
                        "esta especie, etapa y forma de alimento."
                    )
                    for field in missing
                }
            )

        errors = {
            field: (
                "La referencia técnica no aporta un valor para este campo; "
                "indíquelo en la solicitud."
            )
            for field in missing
            if field not in recs
        }
        if errors:
            raise serializers.ValidationError(errors)

    def create(self, validated_data):
        validated_data["is_current"] = True
        validated_data["parent"] = None
        validated_data["version"] = 1
        validated_data["farm"] = self.context["farm"]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        with transaction.atomic():
            old = (
                FeedingSchedule.objects.select_for_update()
                .select_related("farm", "product", "specie", "parent")
                .get(pk=instance.pk)
            )
            if old.deleted_at is not None:
                raise serializers.ValidationError(
                    {"non_field_errors": ["El cronograma no está disponible."]}
                )
            if not old.is_current:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Solo puede versionar el cronograma vigente (is_current). "
                            "Use el último registro de la cadena."
                        ],
                    }
                )
            if old.farm.deleted_at is not None:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "La granja a la que pertenece este cronograma está dada de baja; "
                            "no se pueden crear nuevas versiones."
                        ],
                    }
                )
            create_kwargs = {
                "farm_id": old.farm_id,
                "name": old.name,
                "parent_id": old.pk,
                "version": old.version + 1,
                "is_current": True,
                "product_id": old.product_id,
                "specie_id": old.specie_id,
            }
            for f in FEEDING_SCHEDULE_VERSION_MERGE_FIELDS:
                create_kwargs[f] = (
                    validated_data[f] if f in validated_data else getattr(old, f)
                )
            new_obj = FeedingSchedule.objects.create(**create_kwargs)
            old.is_current = False
            old.deleted_at = timezone.now()
            old.save(update_fields=["is_current", "deleted_at"])
        return new_obj

    @staticmethod
    def _feeding_reference(specie_id, stage, feed_form):
        if specie_id is None or not stage or not feed_form:
            return None
        return SpecieFeedingReference.objects.filter(
            specie_id=specie_id,
            stage=stage,
            recommended_feed_form=feed_form,
        ).first()

    @staticmethod
    def _reference_midpoint(lo, hi):
        if lo is None or hi is None:
            return None
        return ((lo + hi) / 2).quantize(Decimal("0.01"))

    @classmethod
    def reference_recommendations(cls, specie_id, stage, feed_form) -> dict:
        """
        Valores sugeridos desde SpecieFeedingReference.
        Las claves con nombre de campo del cronograma se usan como default al crear (POST).
        recommended_protein_percentage es solo informativo (no existe en FeedingSchedule).
        """
        ref = cls._feeding_reference(specie_id, stage, feed_form)
        if ref is None:
            return {}

        out: dict = {}
        if ref.min_weight_g is not None and ref.max_weight_g is not None:
            out["aceptable_min_weight_g"] = ref.min_weight_g
            out["aceptable_max_weight_g"] = ref.max_weight_g

        if ref.recommended_protein_percentage is not None:
            out["recommended_protein_percentage"] = ref.recommended_protein_percentage

        if ref.recommended_pellet_size_mm is not None:
            out["pellet_size_mm"] = ref.recommended_pellet_size_mm

        if ref.recommended_feeding_rate_percentage is not None:
            out["feeding_rate_percentage"] = ref.recommended_feeding_rate_percentage

        if ref.reference_fca_min is not None and ref.reference_fca_max is not None:
            out["expected_fca"] = cls._reference_midpoint(
                ref.reference_fca_min, ref.reference_fca_max
            )
            out["expected_fca_min"] = ref.reference_fca_min
            out["expected_fca_max"] = ref.reference_fca_max
        if (
            ref.reference_daily_gain_g_min is not None
            and ref.reference_daily_gain_g_max is not None
        ):
            out["expected_daily_gain_g"] = cls._reference_midpoint(
                ref.reference_daily_gain_g_min,
                ref.reference_daily_gain_g_max,
            )
            out["expected_daily_gain_g_min"] = ref.reference_daily_gain_g_min
            out["expected_daily_gain_g_max"] = ref.reference_daily_gain_g_max
        return out

    def get_recommendations(self, obj):
        return self.reference_recommendations(obj.specie_id, obj.type, obj.feed_form)

    @staticmethod
    def reference_warnings(schedule: FeedingSchedule) -> dict[str, str]:
        """
        Compara el schedule con SpecieFeedingReference (misma especie, etapa y forma). Solo se emiten advertencias cuando hay rangos recomendados (min/max) y el dato del schedule queda fuera de esos límites.
        """
        if schedule.specie_id is None or not schedule.type or not schedule.feed_form:
            return {}

        ref = FeedingScheduleSerializer._feeding_reference(
            schedule.specie_id, schedule.type, schedule.feed_form
        )

        if ref is None:
            return {
                "_reference": (
                    "No hay referencia técnica registrada para esta especie, "
                    "etapa y forma de alimento."
                )
            }

        def _fmt_pair(lo, hi):
            return f"{lo} – {hi}"

        def _scalar_outside_range(value, lo, hi) -> bool:
            return (
                value is not None
                and lo is not None
                and hi is not None
                and (value < lo or value > hi)
            )

        def _weight_span_not_inside_reference(s_lo, s_hi, r_lo, r_hi) -> bool:
            return (
                s_lo is not None
                and s_hi is not None
                and r_lo is not None
                and r_hi is not None
                and (s_lo < r_lo or s_hi > r_hi)
            )

        w: dict[str, str] = {}

        if _scalar_outside_range(
            schedule.expected_fca,
            ref.reference_fca_min,
            ref.reference_fca_max,
        ):
            w["expected_fca"] = (
                "Fuera del rango recomendado "
                f"({_fmt_pair(ref.reference_fca_min, ref.reference_fca_max)})."
            )

        if _scalar_outside_range(
            schedule.expected_daily_gain_g,
            ref.reference_daily_gain_g_min,
            ref.reference_daily_gain_g_max,
        ):
            w["expected_daily_gain_g"] = (
                "Fuera del rango recomendado "
                f"({_fmt_pair(ref.reference_daily_gain_g_min, ref.reference_daily_gain_g_max)} g/día)."
            )

        if _weight_span_not_inside_reference(
            schedule.aceptable_min_weight_g,
            schedule.aceptable_max_weight_g,
            ref.min_weight_g,
            ref.max_weight_g,
        ):
            w["aceptable_min_weight_g"] = (
                "El rango de peso aceptable debería estar contenido en el recomendado "
                f"({_fmt_pair(ref.min_weight_g, ref.max_weight_g)} g), según referencia técnica."
            )

        return w

    def get_warnings(self, obj):
        if obj.pk is None:
            return {}
        return self.reference_warnings(obj)


class FeedingPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedingPlan
        fields = [
            "id",
            "farm",
            "cycle",
            "feeding_schedule",
            "start_date",
            "end_date",
            "created_at",
            "deleted_at",
        ]
        read_only_fields = ["farm", "created_at", "deleted_at"]

    def validate(self, data):
        farm = self.context.get("farm")
        farm_id = getattr(farm, "pk", farm) if farm is not None else None
        if farm_id is None:
            raise serializers.ValidationError(
                {"farm": "Contexto de granja requerido para crear el plan."}
            )

        raw_cycle = data.get("cycle")
        raw_schedule = data.get("feeding_schedule")
        cycle_pk = getattr(raw_cycle, "pk", raw_cycle)
        schedule_pk = getattr(raw_schedule, "pk", raw_schedule)

        try:
            cycle = Cycle.objects.select_related("farm", "specie").get(pk=cycle_pk)
        except Cycle.DoesNotExist:
            raise serializers.ValidationError({"cycle": "Ciclo no encontrado."})

        fixed_cycle_id = self.context.get("fixed_cycle_id")
        if fixed_cycle_id is not None and cycle.pk != fixed_cycle_id:
            raise serializers.ValidationError(
                {"cycle": "El ciclo no coincide con el de la URL."}
            )

        try:
            schedule = FeedingSchedule.objects.select_related("farm", "specie").get(
                pk=schedule_pk,
                deleted_at__isnull=True,
                is_current=True,
            )
        except FeedingSchedule.DoesNotExist:
            raise serializers.ValidationError(
                {"feeding_schedule": "Cronograma no encontrado o no disponible."}
            )

        start = data["start_date"]
        end = data["end_date"]
        plan_errors = collect_feeding_plan_business_errors(
            farm_id=farm_id,
            cycle=cycle,
            schedule=schedule,
            start_date=start,
            end_date=end,
        )
        if plan_errors:
            raise serializers.ValidationError(plan_errors)

        if active_plan_date_overlap(
            cycle_id=cycle.pk,
            start_date=start,
            end_date=end,
        ):
            raise serializers.ValidationError(
                {
                    "start_date": FEEDING_PLAN_DATE_OVERLAP_MESSAGE,
                    "end_date": FEEDING_PLAN_DATE_OVERLAP_MESSAGE,
                }
            )

        return data

    def create(self, validated_data):
        validated_data["farm"] = self.context["farm"]
        cycle = validated_data["cycle"]
        with transaction.atomic():
            Cycle.objects.select_for_update().get(pk=cycle.pk)
            if active_plan_date_overlap(
                cycle_id=cycle.pk,
                start_date=validated_data["start_date"],
                end_date=validated_data["end_date"],
            ):
                raise serializers.ValidationError(
                    {
                        "start_date": FEEDING_PLAN_DATE_OVERLAP_MESSAGE,
                        "end_date": FEEDING_PLAN_DATE_OVERLAP_MESSAGE,
                    }
                )
            plan = super().create(validated_data)
            create_feeding_events_for_plan(plan)
        return plan


class FeedingPlanReplaceSerializer(serializers.Serializer):
    cycle = serializers.PrimaryKeyRelatedField(
        queryset=Cycle.objects.filter(deleted_at__isnull=True).select_related(
            "farm", "specie"
        ),
    )
    feeding_schedule = serializers.PrimaryKeyRelatedField(
        queryset=FeedingSchedule.objects.filter(
            deleted_at__isnull=True,
            is_current=True,
        ).select_related("farm", "specie"),
    )
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def validate(self, data):
        old: FeedingPlan = self.context["plan"]
        farm_id = self.context["farm_id"]

        if feeding_plan_lifecycle_state(old) == "finished":
            raise serializers.ValidationError(
                "No se puede modificar un plan cuya fecha de fin ya pasó."
            )

        cycle_obj = Cycle.objects.select_related("farm", "specie").get(
            pk=data["cycle"].pk
        )
        schedule_obj = FeedingSchedule.objects.select_related("farm", "specie").get(
            pk=data["feeding_schedule"].pk,
            deleted_at__isnull=True,
            is_current=True,
        )

        start = data["start_date"]
        end = data["end_date"]

        plan_errors = collect_feeding_plan_business_errors(
            farm_id=farm_id,
            cycle=cycle_obj,
            schedule=schedule_obj,
            start_date=start,
            end_date=end,
        )
        if plan_errors:
            raise serializers.ValidationError(plan_errors)

        state = feeding_plan_lifecycle_state(old)
        if state == "in_progress":
            last_ev = (
                FeedingEvent.objects.filter(
                    feeding_plan_id=old.pk,
                    status__in=(
                        FeedingEvent.Status.COMPLETED,
                        FeedingEvent.Status.SKIPPED,
                    ),
                )
                .order_by("-date", "-scheduled_time", "-ration_number")
                .first()
            )
            if last_ev is None:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Para actualizar un plan en curso debe existir al menos un "
                            "evento de alimentación marcado como completado u omitido. "
                            "Mantenga los eventos del plan al día con la operación real "
                            "(raciones ya ejecutadas u omitidas) y vuelva a intentar."
                        ]
                    }
                )
            if start <= last_ev.date:
                raise serializers.ValidationError(
                    {
                        "start_date": (
                            "La fecha de inicio del nuevo plan debe ser posterior al día "
                            "del último evento completado u omitido."
                        )
                    }
                )

        if active_plan_date_overlap(
            cycle_id=cycle_obj.pk,
            start_date=start,
            end_date=end,
            exclude_plan_ids={old.pk},
        ):
            raise serializers.ValidationError(
                {
                    "start_date": FEEDING_PLAN_DATE_OVERLAP_MESSAGE,
                    "end_date": FEEDING_PLAN_DATE_OVERLAP_MESSAGE,
                }
            )

        return {
            "cycle": cycle_obj,
            "feeding_schedule": schedule_obj,
            "start_date": start,
            "end_date": end,
        }


class FeedingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedingEvent
        fields = [
            "id",
            "farm",
            "cycle",
            "feeding_plan",
            "date",
            "scheduled_time",
            "ration_number",
            "planned_quantity",
            "planned_unit",
            "status",
            "completed_at",
            "actual_quantity",
            "actual_unit",
            "created_at",
            "updated_at",
            "completed_by",
        ]
        read_only_fields = fields


class FeedingEventUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedingEvent
        fields = [
            "status",
            "actual_quantity",
            "actual_unit",
        ]

    def validate_actual_quantity(self, value):
        if value is None:
            raise serializers.ValidationError(
                "La cantidad real es obligatoria y debe ser mayor a 0."
            )
        if value <= 0:
            raise serializers.ValidationError("La cantidad real debe ser mayor a 0.")
        return value

    def validate(self, data):
        instance = self.instance

        if instance.cycle.state != Cycle.State.IN_PROGRESS:
            raise serializers.ValidationError(
                "No se puede modificar un evento de un ciclo que no está en progreso."
            )

        if instance.status == FeedingEvent.Status.SKIPPED:
            raise serializers.ValidationError(
                "No se puede modificar un evento omitido."
            )

        if instance.status == FeedingEvent.Status.COMPLETED:
            if "status" in data:
                if data["status"] == FeedingEvent.Status.SKIPPED:
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
                            "status=skipped para revertir o corrija cantidad y unidad."
                        )
                    }
                )
            if not data:
                raise serializers.ValidationError(
                    "Envíe actual_quantity y/o actual_unit para corregir el registro."
                )
            return data

        # scheduled
        if "status" not in data:
            if "actual_quantity" in data or "actual_unit" in data:
                raise serializers.ValidationError(
                    {
                        "actual_quantity": (
                            "Mientras el evento está programado no se aceptan cantidad ni "
                            "unidad reales sin cerrar el evento. Indique status=completed "
                            "con ambos campos, o status=skipped."
                        )
                    }
                )
            raise serializers.ValidationError(
                {
                    "status": (
                        "Indique status=completed o status=skipped para cerrar el evento."
                    )
                }
            )

        new_status = data["status"]
        if new_status not in (
            FeedingEvent.Status.COMPLETED,
            FeedingEvent.Status.SKIPPED,
        ):
            raise serializers.ValidationError(
                {
                    "status": (
                        "Cuando envía «status», solo se aceptan «completed» o «skipped». "
                        "No use «scheduled»: el evento ya está programado. Otros valores no "
                        "son válidos."
                    )
                }
            )

        if new_status == FeedingEvent.Status.COMPLETED:
            if "actual_quantity" not in data:
                raise serializers.ValidationError(
                    {
                        "actual_quantity": (
                            "Indique la cantidad real al completar el evento."
                        )
                    }
                )

            if "actual_unit" not in data:
                raise serializers.ValidationError(
                    {
                        "actual_unit": (
                            "Indique la unidad de la cantidad real al completar el evento."
                        )
                    }
                )
        elif "actual_quantity" in data or "actual_unit" in data:
            raise serializers.ValidationError(
                {
                    "actual_quantity": (
                        "Para omitir el evento envíe solo status=skipped, sin cantidad ni "
                        "unidad real."
                    )
                }
            )

        return data

    @staticmethod
    def _refresh_monitoring_controls(instance):
        from apps.monitoring.serializers import FishEvaluatedSerializer

        FishEvaluatedSerializer()._refresh_cycle_control_stats_from(
            instance.cycle,
            instance.cycle.pond,
            instance.date,
        )

    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = (
            request.user
            if request and getattr(request.user, "is_authenticated", False)
            else None
        )

        if instance.status == FeedingEvent.Status.COMPLETED:
            if validated_data.get("status") == FeedingEvent.Status.SKIPPED:
                with transaction.atomic():
                    clear_feeding_inventory_for_event(instance.pk)
                    instance.status = FeedingEvent.Status.SKIPPED
                    instance.actual_quantity = None
                    instance.actual_unit = None
                    instance.completed_at = timezone.now()
                    if user is not None:
                        instance.completed_by = user
                    instance.save()
                self._refresh_monitoring_controls(instance)
                return instance

            with transaction.atomic():
                if "actual_quantity" in validated_data:
                    instance.actual_quantity = validated_data["actual_quantity"]
                if "actual_unit" in validated_data:
                    instance.actual_unit = validated_data["actual_unit"]
                if (
                    "actual_quantity" in validated_data
                    or "actual_unit" in validated_data
                ):
                    try:
                        sync_feeding_inventory_for_event(instance)
                    except ValueError as exc:
                        raise serializers.ValidationError({"detail": str(exc)}) from exc
                instance.save()
            self._refresh_monitoring_controls(instance)
            return instance

        new_status = validated_data["status"]

        if new_status == FeedingEvent.Status.COMPLETED:
            with transaction.atomic():
                instance.actual_quantity = validated_data["actual_quantity"]
                instance.actual_unit = validated_data["actual_unit"]
                try:
                    sync_feeding_inventory_for_event(instance)
                except ValueError as exc:
                    raise serializers.ValidationError({"detail": str(exc)}) from exc

                instance.status = new_status
                instance.completed_at = timezone.now()
                if user is not None:
                    instance.completed_by = user
                instance.save()
            self._refresh_monitoring_controls(instance)
            return instance

        with transaction.atomic():
            clear_feeding_inventory_for_event(instance.pk)
            instance.status = new_status
            instance.completed_at = timezone.now()
            if user is not None:
                instance.completed_by = user
            instance.save()
        self._refresh_monitoring_controls(instance)
        return instance
