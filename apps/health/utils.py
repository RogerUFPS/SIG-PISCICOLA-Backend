from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.cycle.models import Cycle, CyclePondBatch
from apps.core.signals import audit_bulk_create, audit_queryset_update
from apps.farms.models import Farm
from apps.feeding.utils import quantity_in_product_unit
from apps.monitoring.models import ControlStat, FishEvaluated
from apps.monitoring.serializers import FishEvaluatedSerializer
from apps.ponds.models import Pond
from apps.purchases.models import InventoryMovement
from apps.purchases.utils import create_out_movement

from .constants import (FISH_EVALUATED_TYPE_HEALTH_STAT,
                        TREATMENT_PLAN_PRODUCT_TYPE_NAMES)
from .models import HealthStat, TreatmentEvent, TreatmentPlan

HEALTH_STAT_DELETE_HAS_PLANS_MESSAGE = (
    "No puede eliminar un registro de salud con planes de tratamiento asociados."
)
HEALTH_STAT_DELETE_HAS_FISH_EVALUATION_MESSAGE = (
    "No puede eliminar un registro de salud vinculado a una evaluación de peces."
)
HEALTH_STAT_DELETE_CONFIRM_REQUIRED_MESSAGE = (
    "El borrado es definitivo (no hay recuperación). "
    "Confirme en la interfaz y envíe ?confirm=true."
)


def _fish_evaluations_qs(*, cycle, pond, **filters):
    return FishEvaluated.objects.filter(
        cycle=cycle,
        pond=pond,
        deleted_at__isnull=True,
        **filters,
    )


def link_fish_evaluation_to_health_stat(
    *,
    fish_evaluation: FishEvaluated,
    health_stat: HealthStat,
    created_by=None,
) -> FishEvaluated:
    """Vincula la evaluación de peces al registro de salud (type + source_id)."""
    update_fields = []
    if fish_evaluation.type != FishEvaluated.Type.HEALTH_STAT:
        fish_evaluation.type = FishEvaluated.Type.HEALTH_STAT
        update_fields.append("type")
    if fish_evaluation.source_id != health_stat.pk:
        fish_evaluation.source_id = health_stat.pk
        update_fields.append("source_id")
    if fish_evaluation.farm_id != health_stat.farm_id:
        fish_evaluation.farm_id = health_stat.farm_id
        update_fields.append("farm")
    if created_by is not None:
        user_id = getattr(created_by, "pk", created_by)
        if fish_evaluation.created_by_id != user_id:
            fish_evaluation.created_by_id = user_id
            update_fields.append("created_by")
    if update_fields:
        fish_evaluation.save(update_fields=update_fields)
    return fish_evaluation


def collect_health_stat_scope_errors(*, farm, cycle, pond, stat_date) -> dict:
    errors = {}

    if cycle.state != Cycle.State.IN_PROGRESS:
        errors["cycle"] = "El ciclo debe estar en estado IN_PROGRESS."

    if pond.status != Pond.Status.IN_USE:
        errors["pond"] = "El estanque debe estar en estado IN_USE."

    if cycle.farm_id != farm.pk:
        errors["farm"] = "El ciclo no pertenece a la granja indicada."

    if pond.farm_id != farm.pk:
        errors["pond"] = "El estanque no pertenece a la granja indicada."

    if not CyclePondBatch.objects.filter(cycle=cycle, pond_batch__pond=pond).exists():
        errors["pond"] = "El estanque no está asociado a este ciclo."

    if stat_date and stat_date > date.today():
        errors["date"] = "La fecha del registro de salud no puede ser futura."

    return errors


def collect_disease_name_errors(disease_name) -> dict:
    if disease_name is not None and not str(disease_name).strip():
        return {"disease_name": "El nombre de la enfermedad es obligatorio."}
    return {}


def health_stat_has_treatment_plans(health_stat_id: int) -> bool:
    return TreatmentPlan.objects.filter(health_stat_id=health_stat_id).exists()


def health_stat_has_linked_fish_evaluation(health_stat_id: int) -> bool:
    return FishEvaluated.objects.filter(
        type=FISH_EVALUATED_TYPE_HEALTH_STAT,
        source_id=health_stat_id,
        deleted_at__isnull=True,
    ).exists()


def health_stat_delete_blockers(health_stat_id: int) -> list[str]:
    """Motivos por los que no se puede borrar un HealthStat (vacío = permitido)."""
    blockers = []
    if health_stat_has_treatment_plans(health_stat_id):
        blockers.append(HEALTH_STAT_DELETE_HAS_PLANS_MESSAGE)
    if health_stat_has_linked_fish_evaluation(health_stat_id):
        blockers.append(HEALTH_STAT_DELETE_HAS_FISH_EVALUATION_MESSAGE)
    return blockers


def collect_health_stat_update_errors(*, health_stat: HealthStat, data: dict) -> dict:
    """Valida PATCH de HealthStat (campos acotados)."""
    errors = {}

    if "disease_name" in data:
        errors.update(collect_disease_name_errors(data["disease_name"]))

    if "date" in data and data["date"] != health_stat.date:
        if health_stat_has_treatment_plans(health_stat.pk):
            errors["date"] = (
                "No puede cambiar la fecha si el registro tiene planes de tratamiento."
            )
        else:
            errors.update(
                collect_health_stat_scope_errors(
                    farm=health_stat.farm,
                    cycle=health_stat.cycle,
                    pond=health_stat.pond,
                    stat_date=data["date"],
                )
            )

    return errors


def collect_prior_fish_evaluation_errors(*, cycle, pond, stat_date) -> dict:
    has_eval = _fish_evaluations_qs(
        cycle=cycle,
        pond=pond,
        evaluation_date__lte=stat_date,
    ).exists()
    if not has_eval:
        return {
            "date": (
                "Debe existir al menos una evaluación de peces previa "
                "a la fecha del registro de salud."
            )
        }
    return {}


def build_fish_evaluated_payload(
    *,
    cycle,
    pond,
    stat_date,
    fish: dict,
    farm=None,
) -> dict:
    """Arma el body que espera ``FishEvaluatedSerializer`` (monitoring)."""
    eval_date = fish.get("evaluation_date") or stat_date
    payload = {
        "cycle": cycle.pk,
        "pond": pond.pk,
        "evaluation_date": eval_date,
        "sampled_quantity": fish["sampled_quantity"],
        "mortality_quantity": fish.get("mortality_quantity", 0),
        "min_weight_g": fish["min_weight_g"],
        "max_weight_g": fish["max_weight_g"],
        "observations": fish.get("observations"),
        "type": FISH_EVALUATED_TYPE_HEALTH_STAT,
    }
    if farm is not None:
        payload["farm"] = getattr(farm, "pk", farm)
    if fish.get("batch_id") is not None:
        payload["batch_id"] = fish["batch_id"]
    return payload


def is_combined_health_stat_payload(data: dict) -> bool:
    """POST con muestreo + diagnóstico en un solo formulario (body plano)."""
    return "sampled_quantity" in data


def pop_fish_evaluation_fields(data: dict) -> tuple[dict, dict | None]:
    """
    Quita del body los campos write-only de evaluación de peces.

    Si el POST incluye ``sampled_quantity`` (formulario combinado), devuelve
    esos campos en ``fish``; si no, los descarta para no pasarlos a HealthStat.
    """
    from .constants import FISH_EVALUATION_CREATE_FIELDS

    fish = {}
    for key in FISH_EVALUATION_CREATE_FIELDS:
        if key in data:
            fish[key] = data.pop(key)
    if "sampled_quantity" not in fish:
        return data, None
    return data, fish


def validate_fish_evaluation_with_monitoring(
    *,
    cycle,
    pond,
    stat_date,
    fish: dict,
    serializer_context: dict,
) -> dict:
    """Valida el muestreo del POST combinado con ``FishEvaluatedSerializer``."""
    from apps.monitoring.serializers import FishEvaluatedSerializer

    if "sampled_quantity" not in fish:
        return {"sampled_quantity": "Este campo es obligatorio."}

    payload = build_fish_evaluated_payload(
        cycle=cycle,
        pond=pond,
        stat_date=stat_date,
        fish=fish,
        farm=serializer_context.get("farm"),
    )
    eval_serializer = FishEvaluatedSerializer(
        data=payload,
        context=serializer_context,
    )
    if not eval_serializer.is_valid():
        return eval_serializer.errors
    return {}


def collect_fish_evaluation_duplicate_errors(
    *,
    cycle,
    pond,
    eval_date,
) -> dict:
    """
    Detecta colisión de fecha en evaluaciones de peces.

    Incluye registros con soft-delete: si la BD aún tiene unique
    (cycle, evaluation_date, pond), un INSERT nuevo dispara IntegrityError.
    """
    rows = FishEvaluated.objects.filter(
        cycle=cycle,
        pond=pond,
        evaluation_date=eval_date,
    )
    if not rows.exists():
        return {}

    if rows.filter(deleted_at__isnull=True).exists():
        return {
            "date": (
                f"Ya existe una evaluación de peces para el {eval_date} "
                "en este ciclo y estanque."
            ),
        }

    return {}


def collect_combined_health_stat_payload_errors(
    *,
    cycle,
    pond,
    stat_date,
    disease_name,
    fish: dict,
) -> dict:
    errors = collect_disease_name_errors(disease_name)

    eval_date = fish.get("evaluation_date") or stat_date
    if eval_date > stat_date:
        errors["date"] = (
            "La fecha del muestreo no puede ser posterior a la fecha del registro de salud."
        )

    errors.update(
        collect_fish_evaluation_duplicate_errors(
            cycle=cycle,
            pond=pond,
            eval_date=eval_date,
        )
    )

    return errors


def create_health_stat(*, validated_data, created_by) -> HealthStat:
    return HealthStat.objects.create(**validated_data, created_by=created_by)


def _remove_soft_deleted_fish_evaluations(*, cycle, pond, eval_date) -> None:
    """Libera la fecha si quedó una evaluación con soft-delete (unique en BD)."""
    FishEvaluated.objects.filter(
        cycle=cycle,
        pond=pond,
        evaluation_date=eval_date,
        deleted_at__isnull=False,
    ).delete()


def _prepare_control_stat_slot(*, cycle, pond, eval_date) -> None:
    """
    FishEvaluatedSerializer (monitoring) hace update_or_create de ControlStat.
    Si el del día está archivado (soft-delete), reactivarlo antes del save.
    """
    audit_queryset_update(
        ControlStat.objects.filter(
            cycle=cycle,
            pond=pond,
            control_date=eval_date,
            deleted_at__isnull=False,
        ),
        deleted_at=None,
    )


def create_health_stat_with_fish_evaluation(
    *,
    validated_data: dict,
    fish: dict,
    created_by,
    serializer_context: dict,
) -> dict:
    cycle = validated_data["cycle"]
    pond = validated_data["pond"]
    stat_date = validated_data["date"]

    try:
        with transaction.atomic():
            health_stat = create_health_stat(
                validated_data=validated_data,
                created_by=created_by,
            )

            payload = build_fish_evaluated_payload(
                cycle=cycle,
                pond=pond,
                stat_date=stat_date,
                fish=fish,
                farm=validated_data.get("farm"),
            )
            eval_date = fish.get("evaluation_date") or stat_date
            _remove_soft_deleted_fish_evaluations(
                cycle=cycle,
                pond=pond,
                eval_date=eval_date,
            )
            _prepare_control_stat_slot(
                cycle=cycle,
                pond=pond,
                eval_date=eval_date,
            )

            eval_serializer = FishEvaluatedSerializer(
                data=payload,
                context=serializer_context,
            )
            eval_serializer.is_valid(raise_exception=True)
            # cycle/pond son read_only en monitoring; hay que pasarlos en save()
            # (igual que FishEvaluatedViewSet.perform_create).
            fish_evaluation = eval_serializer.save(
                cycle=cycle,
                pond=pond,
                farm=validated_data.get("farm"),
                created_by=created_by,
            )
            link_fish_evaluation_to_health_stat(
                fish_evaluation=fish_evaluation,
                health_stat=health_stat,
                created_by=created_by,
            )
    except IntegrityError as exc:
        eval_date = fish.get("evaluation_date") or stat_date
        duplicate_errors = collect_fish_evaluation_duplicate_errors(
            cycle=cycle,
            pond=pond,
            eval_date=eval_date,
        )
        if duplicate_errors:
            raise ValueError(duplicate_errors) from exc
        raise ValueError(
            {
                "detail": (
                    "No se pudo guardar la evaluación de peces por un conflicto "
                    "con datos existentes (fecha, ciclo o estanque). "
                    "Revise que no haya registros duplicados y que las migraciones "
                    "estén aplicadas."
                ),
            }
        ) from exc

    return {"health_stat": health_stat, "fish_evaluation": fish_evaluation}


def _plan_has_scheduled_events(plan_id: int) -> bool:
    return TreatmentEvent.objects.filter(
        treatment_plan_id=plan_id,
        status=TreatmentEvent.Status.SCHEDULED,
    ).exists()


def sync_treatment_plan_status(
    plan: TreatmentPlan,
    today=None,
    *,
    save: bool = True,
) -> TreatmentPlan:
    today = today or timezone.now().date()
    if plan.status == TreatmentPlan.Status.CANCELLED:
        return plan

    if today < plan.start_date:
        new_status = TreatmentPlan.Status.SCHEDULED
    elif plan.start_date <= today <= plan.end_date:
        new_status = TreatmentPlan.Status.IN_PROGRESS
    elif _plan_has_scheduled_events(plan.pk):
        new_status = TreatmentPlan.Status.IN_PROGRESS
    else:
        new_status = TreatmentPlan.Status.COMPLETED

    if new_status != plan.status:
        plan.status = new_status
        if save:
            plan.save(update_fields=["status", "updated_at"])
    return plan


def sync_treatment_plan_queryset(qs, today=None):
    for plan in qs:
        sync_treatment_plan_status(plan, today=today)


def treatment_plan_lifecycle_state(plan: TreatmentPlan, today=None) -> str:
    plan = sync_treatment_plan_status(plan, today=today)
    if plan.status == TreatmentPlan.Status.CANCELLED:
        return "cancelled"
    if plan.status == TreatmentPlan.Status.COMPLETED:
        return "finished"
    if plan.status == TreatmentPlan.Status.IN_PROGRESS:
        return "in_progress"
    return "scheduled"


def active_treatment_plan_date_overlap(
    *,
    health_stat_id: int,
    start_date,
    end_date,
    exclude_plan_ids: set | None = None,
) -> bool:
    qs = TreatmentPlan.objects.filter(
        health_stat_id=health_stat_id,
        status__in=(
            TreatmentPlan.Status.SCHEDULED,
            TreatmentPlan.Status.IN_PROGRESS,
            TreatmentPlan.Status.COMPLETED,
        ),
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if exclude_plan_ids:
        qs = qs.exclude(pk__in=exclude_plan_ids)
    return qs.exists()


def treatment_product_type_error(product) -> str | None:
    """None si el tipo de producto es válido para tratamiento; mensaje si no."""
    if product is None:
        return None
    type_name = getattr(
        getattr(product, "type_product", None),
        "name",
        None,
    )
    if not type_name:
        return (
            "El producto debe tener un tipo de producto configurado "
            "(medicamento / medicación)."
        )
    normalized = type_name.casefold()
    if any(
        normalized == allowed.casefold()
        for allowed in TREATMENT_PLAN_PRODUCT_TYPE_NAMES
    ):
        return None
    return (
        "El tipo de producto debe ser de medicación permitida para planes de tratamiento "
        f"(recibido: «{type_name}»)."
    )


def collect_treatment_plan_business_errors(
    *,
    farm_id: int,
    health_stat: HealthStat,
    product,
    start_date,
    end_date,
    times_per_day: int,
    gap_between_times_per_day: int,
    gap_between_completed_day: int,
    dose_per_application,
) -> dict:
    errors = {}
    try:
        Farm.objects.get(pk=farm_id, deleted_at__isnull=True)
    except Farm.DoesNotExist:
        errors["farm"] = "La granja no existe o no está disponible."

    if health_stat.farm_id != farm_id:
        errors["health_stat"] = (
            "El registro de salud debe pertenecer a la misma granja."
        )

    cycle = health_stat.cycle
    pond = health_stat.pond
    if cycle.deleted_at:
        errors["health_stat"] = "El ciclo del registro de salud no está disponible."
    if cycle.state in (Cycle.State.FINISHED, Cycle.State.CANCELLED):
        errors["health_stat"] = (
            "No se puede asociar un plan a un ciclo finalizado o cancelado."
        )
    if cycle.state != Cycle.State.IN_PROGRESS:
        errors["health_stat"] = "El ciclo debe estar en estado IN_PROGRESS."
    if pond.status != Pond.Status.IN_USE:
        errors["health_stat"] = "El estanque del registro debe estar en estado IN_USE."

    if start_date > end_date:
        errors["end_date"] = "La fecha de fin debe ser mayor o igual al inicio."
    if start_date < health_stat.date:
        errors["start_date"] = (
            "El inicio del plan no puede ser anterior a la fecha del registro de salud."
        )
    if start_date < cycle.start_date:
        errors["start_date"] = (
            "El inicio del plan no puede ser anterior al inicio del ciclo."
        )
    if end_date > cycle.estimated_finish_date:
        errors["end_date"] = (
            "La fecha de fin no puede superar la fecha estimada de fin del ciclo."
        )
    if cycle.finish_date and end_date > cycle.finish_date:
        errors["end_date"] = (
            "La fecha de fin no puede superar la fecha de cierre del ciclo."
        )

    if times_per_day < 1:
        errors["times_per_day"] = "Debe haber al menos una aplicación por día."
    if gap_between_times_per_day < 0:
        errors["gap_between_times_per_day"] = "No puede ser negativo."
    if gap_between_completed_day < 0:
        errors["gap_between_completed_day"] = "No puede ser negativo."
    if dose_per_application is not None and dose_per_application <= 0:
        errors["dose_per_application"] = "La dosis debe ser mayor a cero."

    if product is not None:
        if product.deleted_at is not None:
            errors["product"] = "El producto no está disponible."
        elif product.farm_id != farm_id:
            errors["product"] = "El producto debe pertenecer a la misma granja."
        else:
            type_err = treatment_product_type_error(product)
            if type_err:
                errors["product"] = type_err

    return errors


def create_treatment_events_for_plan(plan: TreatmentPlan) -> int:
    health_stat = HealthStat.objects.select_related("cycle").get(pk=plan.health_stat_id)
    day_stride = plan.gap_between_completed_day + 1
    first_application_time = time(0, 0)

    events: list[TreatmentEvent] = []
    application_number = 1
    day_index = 0
    current = plan.start_date

    while current <= plan.end_date:
        if day_index % day_stride == 0:
            base = datetime.combine(current, first_application_time)
            for i in range(plan.times_per_day):
                st = base + timedelta(minutes=i * plan.gap_between_times_per_day)
                events.append(
                    TreatmentEvent(
                        farm_id=plan.farm_id,
                        cycle_id=health_stat.cycle_id,
                        treatment_plan=plan,
                        date=st.date(),
                        scheduled_time=st.time(),
                        application_number=application_number,
                        planned_dose=plan.dose_per_application,
                        planned_unit_id=plan.unit_id,
                        status=TreatmentEvent.Status.SCHEDULED,
                    )
                )
                application_number += 1
        current += timedelta(days=1)
        day_index += 1

    if not events:
        return 0
    audit_bulk_create(TreatmentEvent, events)
    return len(events)


def _last_completed_or_skipped_treatment_event(plan_id: int):
    return (
        TreatmentEvent.objects.filter(
            treatment_plan_id=plan_id,
            status__in=(
                TreatmentEvent.Status.COMPLETED,
                TreatmentEvent.Status.SKIPPED,
            ),
        )
        .order_by("-date", "-scheduled_time", "-application_number")
        .first()
    )


def _create_treatment_plan_with_events_locked(
    *,
    farm_id: int,
    health_stat: HealthStat,
    created_by,
    exclude_plan_ids: set | None = None,
    **plan_fields,
) -> TreatmentPlan:
    if active_treatment_plan_date_overlap(
        health_stat_id=health_stat.pk,
        start_date=plan_fields["start_date"],
        end_date=plan_fields["end_date"],
        exclude_plan_ids=exclude_plan_ids,
    ):
        raise ValueError(
            "Las fechas se solapan con otro plan vigente del mismo registro de salud."
        )

    plan = TreatmentPlan.objects.create(
        farm_id=farm_id,
        health_stat=health_stat,
        created_by=created_by,
        status=TreatmentPlan.Status.SCHEDULED,
        **plan_fields,
    )
    create_treatment_events_for_plan(plan)
    return plan


def update_in_progress_treatment_plan(
    *,
    farm_id: int,
    old_plan: TreatmentPlan,
    health_stat: HealthStat,
    created_by,
    exclude_plan_ids: set | None = None,
    **plan_fields,
) -> TreatmentPlan:
    with transaction.atomic():
        locked_old = TreatmentPlan.objects.select_for_update().get(pk=old_plan.pk)
        sync_treatment_plan_status(locked_old, save=True)
        if locked_old.status == TreatmentPlan.Status.CANCELLED:
            raise ValueError("El plan ya fue cancelado.")
        if locked_old.status == TreatmentPlan.Status.COMPLETED:
            raise ValueError("No se puede modificar un plan terminado.")
        if locked_old.status != TreatmentPlan.Status.IN_PROGRESS:
            raise ValueError("El plan no está en curso.")
        if locked_old.farm_id != farm_id:
            raise ValueError("Inconsistencia de granja del plan.")

        last_ev = _last_completed_or_skipped_treatment_event(locked_old.pk)
        if last_ev is None:
            raise ValueError(
                "Para actualizar un plan en curso debe existir al menos un evento "
                "marcado como completado u omitido."
            )

        locked_old.end_date = last_ev.date
        locked_old.status = TreatmentPlan.Status.COMPLETED
        locked_old.save(update_fields=["end_date", "status"])

        TreatmentEvent.objects.filter(
            treatment_plan_id=locked_old.pk,
            status=TreatmentEvent.Status.SCHEDULED,
        ).filter(
            Q(date__gt=last_ev.date)
            | Q(date=last_ev.date, scheduled_time__gt=last_ev.scheduled_time)
            | Q(
                date=last_ev.date,
                scheduled_time=last_ev.scheduled_time,
                application_number__gt=last_ev.application_number,
            )
        ).delete()

        exclude = {locked_old.pk}
        if exclude_plan_ids:
            exclude |= exclude_plan_ids

        new_plan = _create_treatment_plan_with_events_locked(
            farm_id=farm_id,
            health_stat=health_stat,
            created_by=created_by,
            exclude_plan_ids=exclude,
            **plan_fields,
        )
    return new_plan


def update_scheduled_treatment_plan(
    *,
    farm_id: int,
    plan: TreatmentPlan,
    health_stat: HealthStat,
    **plan_fields,
) -> TreatmentPlan:
    with transaction.atomic():
        locked = TreatmentPlan.objects.select_for_update().get(pk=plan.pk)
        sync_treatment_plan_status(locked, save=True)
        if locked.status != TreatmentPlan.Status.SCHEDULED:
            raise ValueError("Solo se puede modificar un plan en estado programado.")
        if locked.status == TreatmentPlan.Status.CANCELLED:
            raise ValueError("El plan ya fue cancelado.")
        if locked.farm_id != farm_id:
            raise ValueError("Inconsistencia de granja del plan.")

        if active_treatment_plan_date_overlap(
            health_stat_id=health_stat.pk,
            start_date=plan_fields["start_date"],
            end_date=plan_fields["end_date"],
            exclude_plan_ids={locked.pk},
        ):
            raise ValueError(
                "Las fechas se solapan con otro plan vigente del mismo registro de salud."
            )

        TreatmentEvent.objects.filter(treatment_plan_id=locked.pk).delete()
        for field, value in plan_fields.items():
            setattr(locked, field, value)
        locked.health_stat = health_stat
        locked.status = TreatmentPlan.Status.SCHEDULED
        locked.save()
        create_treatment_events_for_plan(locked)
    return locked


def _health_out_movement_for_event(event_id: int):
    return InventoryMovement.objects.filter(
        source_type=InventoryMovement.SourceType.HEALTH,
        source_id=event_id,
        movement_type=InventoryMovement.MovementType.OUT,
    ).first()


def _delete_health_out_movement(event_id: int) -> None:
    InventoryMovement.objects.filter(
        source_type=InventoryMovement.SourceType.HEALTH,
        source_id=event_id,
        movement_type=InventoryMovement.MovementType.OUT,
    ).delete()


def clear_treatment_inventory_for_event(event_id: int) -> None:
    """Elimina la salida de inventario del evento (p. ej. al omitir o revertir)."""
    _delete_health_out_movement(event_id)


def sync_treatment_inventory_for_event(treatment_event: TreatmentEvent):
    """
    Alinea el movimiento OUT de inventario con la dosis real del evento.

    Elimina y recrea el movimiento si la cantidad cambió (p. ej. corrección).
    """
    te = TreatmentEvent.objects.select_related(
        "farm",
        "cycle",
        "actual_unit",
        "treatment_plan__product",
        "treatment_plan__product__type_product",
        "treatment_plan__product__unit",
        "treatment_plan__health_stat",
        "treatment_plan__health_stat__pond",
    ).get(pk=treatment_event.pk)

    product = te.treatment_plan.product
    if product is None:
        _delete_health_out_movement(te.pk)
        return None

    if product.deleted_at is not None:
        raise ValueError("El producto del plan de tratamiento no está disponible.")

    type_err = treatment_product_type_error(product)
    if type_err:
        raise ValueError(type_err)

    if treatment_event.actual_dose is None or treatment_event.actual_unit is None:
        raise ValueError(
            "La dosis real y la unidad son obligatorias para descontar inventario."
        )

    qty_stock = quantity_in_product_unit(
        Decimal(str(treatment_event.actual_dose)),
        treatment_event.actual_unit,
        product.unit,
    )
    existing = _health_out_movement_for_event(te.pk)
    if existing is not None:
        if Decimal(str(existing.quantity)) == qty_stock:
            return existing
        _delete_health_out_movement(te.pk)

    return create_out_movement(
        farm=te.farm,
        product=product,
        quantity=float(qty_stock),
        source_type=InventoryMovement.SourceType.HEALTH,
        source_id=te.pk,
        pond=te.treatment_plan.health_stat.pond,
        cycle=te.cycle,
        observations=(
            f"Tratamiento — aplicación {te.application_number} "
            f"({te.date} {te.scheduled_time})"
        ),
    )


def register_treatment_consume(treatment_event: TreatmentEvent):
    """Descuenta inventario al completar (idempotente si ya está sincronizado)."""
    return sync_treatment_inventory_for_event(treatment_event)


def collect_treatment_event_close_errors(event: TreatmentEvent, *, now=None) -> dict:
    """
    Valida que un evento programado pueda cerrarse (completed/skipped).

    ``scheduled_time`` no bloquea el cierre el mismo día; sirve para orden/UI/alertas.
    """
    today = (now or timezone.now()).date()

    if event.status != TreatmentEvent.Status.SCHEDULED:
        return {}

    if event.date > today:
        return {"status": ("No puede cerrar un evento con fecha futura.")}

    plan = TreatmentPlan.objects.get(pk=event.treatment_plan_id)
    sync_treatment_plan_status(plan)
    if plan.status == TreatmentPlan.Status.CANCELLED:
        return {"status": "No puede modificar eventos de un plan cancelado."}
    if plan.status == TreatmentPlan.Status.COMPLETED:
        return {"status": "No puede modificar eventos de un plan terminado."}
    if plan.status == TreatmentPlan.Status.SCHEDULED:
        return {
            "status": (
                "No puede cerrar eventos mientras el plan sigue programado "
                "(aún no ha iniciado)."
            )
        }

    return {}


def cancel_treatment_plan(plan: TreatmentPlan) -> None:
    with transaction.atomic():
        locked = TreatmentPlan.objects.select_for_update().get(pk=plan.pk)
        if locked.status == TreatmentPlan.Status.CANCELLED:
            raise ValueError("El plan ya fue cancelado.")
        sync_treatment_plan_status(locked, save=True)
        if locked.status != TreatmentPlan.Status.SCHEDULED:
            raise ValueError(
                "Solo se puede cancelar un plan en estado programado. "
                "Los planes en curso o terminados se conservan por trazabilidad."
            )
        locked.status = TreatmentPlan.Status.CANCELLED
        locked.save(update_fields=["status", "updated_at"])
        TreatmentEvent.objects.filter(
            treatment_plan_id=locked.pk,
            status=TreatmentEvent.Status.SCHEDULED,
        ).delete()
