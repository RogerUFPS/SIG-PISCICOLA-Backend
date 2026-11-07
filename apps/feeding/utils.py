from __future__ import annotations
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.cycle.models import Cycle, CyclePondBatch
from apps.core.signals import audit_bulk_create
from apps.farms.models import Farm
from apps.purchases.models import InventoryMovement
from apps.purchases.utils import create_out_movement
from apps.monitoring.services import BiomassCalculator


from .constants import FEED_SCHEDULE_PRODUCT_TYPE_NAMES
from .models import FeedingEvent, FeedingPlan, FeedingSchedule


_MASS_GRAMS_PER_UNIT_SYMBOL = {
    "mg": Decimal("0.001"),
    "g": Decimal("1"),
    "gr": Decimal("1"),
    "kg": Decimal("1000"),
    "t": Decimal("1000000"),
    "ton": Decimal("1000000"),
}


def normalize_unit_symbol(symbol: str | None) -> str:
    """
    Normaliza símbolos de unidad para comparar (p. ej. ``"Kg"`` en BD → ``"kg"``).
    """
    return (symbol or "").strip().lower()


def _mass_grams_per_unit_symbol(unit) -> Decimal | None:
    if unit is None:
        return None
    key = normalize_unit_symbol(getattr(unit, "symbol", None))
    if not key:
        return None
    return _MASS_GRAMS_PER_UNIT_SYMBOL.get(key)


def quantity_in_product_unit(
    quantity: Decimal,
    from_unit,
    to_unit,
) -> Decimal:
    """
    Convierte una cantidad de masa desde ``from_unit`` hacia ``to_unit`` (unidad del producto).

    Si las unidades coinciden, devuelve ``quantity``. Si no, usa factores solo para
    símbolos de masa conocidos (mg, g, kg, t). Si no puede convertir, lanza ``ValueError``.
    """
    if from_unit is None or to_unit is None:
        raise ValueError(
            "Faltan unidades para alinear la cantidad consumida con el inventario del producto."
        )
    if from_unit.pk == to_unit.pk:
        return quantity
    g_from = _mass_grams_per_unit_symbol(from_unit)
    g_to = _mass_grams_per_unit_symbol(to_unit)
    if g_from is None or g_to is None:
        raise ValueError(
            "No se puede convertir entre la unidad indicada y la unidad del producto "
            f"({getattr(to_unit, 'symbol', '')}). Use la misma unidad que el producto o "
            "unidades de masa estándar (mg, g, kg, t)."
        )
    out = quantity * g_from / g_to
    return out.quantize(Decimal("0.0001"))


def active_plan_date_overlap(
    *,
    cycle_id: int,
    start_date,
    end_date,
    exclude_plan_ids: set | None = None,
) -> bool:
    qs = FeedingPlan.objects.filter(
        cycle_id=cycle_id,
        deleted_at__isnull=True,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if exclude_plan_ids:
        qs = qs.exclude(pk__in=exclude_plan_ids)
    return qs.exists()


def feeding_plan_lifecycle_state(plan: FeedingPlan, today=None):
    today = today or timezone.now().date()
    if plan.end_date < today:
        return "finished"
    if plan.start_date <= today <= plan.end_date:
        return "in_progress"
    return "scheduled"


def collect_feeding_plan_business_errors(
    *,
    farm_id: int,
    cycle: Cycle,
    schedule: FeedingSchedule,
    start_date,
    end_date,
) -> dict:
    errors = {}
    try:
        Farm.objects.get(pk=farm_id, deleted_at__isnull=True)
    except Farm.DoesNotExist:
        errors["farm"] = "La granja no existe o no está disponible."

    if cycle.deleted_at:
        errors["cycle"] = "El ciclo no está disponible."
    if getattr(cycle, "farm", None) and cycle.farm.deleted_at:
        errors["cycle"] = "La granja asociada al ciclo no está disponible."
    if schedule.deleted_at is not None:
        errors["feeding_schedule"] = "El cronograma no está disponible."
    if getattr(schedule, "farm", None) and schedule.farm.deleted_at:
        errors["feeding_schedule"] = (
            "La granja asociada al cronograma no está disponible."
        )
    if cycle.farm_id != farm_id:
        errors["cycle"] = "El ciclo debe pertenecer a la misma granja."
    if schedule.farm_id != farm_id:
        errors["feeding_schedule"] = "El cronograma debe pertenecer a la misma granja."
    if cycle.specie_id != schedule.specie_id:
        errors["feeding_schedule"] = (
            "La especie del cronograma debe coincidir con la del ciclo."
        )

    biological_states = set(
        CyclePondBatch.objects.filter(cycle_id=cycle.pk).values_list(
            "pond_batch__batch__biological_state", flat=True
        )
    )
    if not biological_states:
        errors["feeding_schedule"] = (
            "No se puede validar la etapa del cronograma porque el ciclo no tiene "
            "un lote asociado."
        )
    elif len(biological_states) > 1:
        errors["feeding_schedule"] = (
            "El ciclo contiene lotes con etapas biológicas diferentes; corrija esa "
            "inconsistencia antes de asignar un cronograma."
        )
    else:
        biological_state = next(iter(biological_states))
        if schedule.type != biological_state:
            errors["feeding_schedule"] = (
                "El cronograma no es compatible con la etapa biológica del ciclo "
                f"({biological_state})."
            )
    if cycle.state in (Cycle.State.FINISHED, Cycle.State.CANCELLED):
        errors["cycle"] = (
            "No se puede asociar un plan a un ciclo finalizado o cancelado."
        )
    if start_date > end_date:
        errors["end_date"] = "La fecha de fin debe ser mayor o igual al inicio."
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
    return errors


def _feeding_out_movement_for_event(event_id: int):
    return InventoryMovement.objects.filter(
        source_type=InventoryMovement.SourceType.FEEDING,
        source_id=event_id,
        movement_type=InventoryMovement.MovementType.OUT,
    ).first()


def _delete_feeding_out_movement(event_id: int) -> None:
    InventoryMovement.objects.filter(
        source_type=InventoryMovement.SourceType.FEEDING,
        source_id=event_id,
        movement_type=InventoryMovement.MovementType.OUT,
    ).delete()


def clear_feeding_inventory_for_event(event_id: int) -> None:
    """Elimina la salida de inventario del evento (p. ej. al omitir o revertir)."""
    _delete_feeding_out_movement(event_id)


def sync_feeding_inventory_for_event(feeding_event: FeedingEvent):
    """
    Alinea el movimiento OUT de inventario con la cantidad real del evento.

    Elimina y recrea el movimiento si la cantidad cambió (p. ej. corrección).
    """
    try:
        fe = FeedingEvent.objects.select_related(
            "farm",
            "cycle",
            "cycle__pond",
            "actual_unit",
            "feeding_plan__feeding_schedule__product",
            "feeding_plan__feeding_schedule__product__unit",
        ).get(pk=feeding_event.pk)
    except FeedingEvent.DoesNotExist:
        raise ValueError("El evento de alimentación no existe.") from None

    product = fe.feeding_plan.feeding_schedule.product
    if product.deleted_at is not None:
        raise ValueError("El producto del cronograma no está disponible.")

    if feeding_event.actual_quantity is None or feeding_event.actual_unit is None:
        raise ValueError(
            "La cantidad real y la unidad son obligatorias para descontar inventario."
        )

    qty_stock = quantity_in_product_unit(
        Decimal(str(feeding_event.actual_quantity)),
        feeding_event.actual_unit,
        product.unit,
    )
    existing = _feeding_out_movement_for_event(fe.pk)
    if existing is not None:
        if Decimal(str(existing.quantity)) == qty_stock:
            return existing
        _delete_feeding_out_movement(fe.pk)

    return create_out_movement(
        farm=fe.farm,
        product=product,
        quantity=float(qty_stock),
        source_type=InventoryMovement.SourceType.FEEDING,
        source_id=fe.pk,
        pond=fe.cycle.pond,
        cycle=fe.cycle,
        observations=(
            f"Alimentación — ración {fe.ration_number} "
            f"({fe.date} {fe.scheduled_time})"
        ),
    )


def register_feeding_consume(feeding_event: FeedingEvent):
    """Descuenta inventario al completar (idempotente si ya está sincronizado)."""
    return sync_feeding_inventory_for_event(feeding_event)


def cycle_fish_count_and_avg_weight_g(cycle_id: int) -> tuple[Decimal, Decimal] | None:
    """
    Peces vivos y peso promedio ponderado del ciclo.

    Usa ``pond_batch.current_quantity`` (stock operativo) y ``avg_weight_g`` de
    cada ``CyclePondBatch``.
    """
    rows = list(
        CyclePondBatch.objects.filter(cycle_id=cycle_id).values_list(
            "pond_batch__current_quantity", "avg_weight_g"
        )
    )
    if not rows:
        return None
    total_fish = sum(int(q) for q, _ in rows)
    if total_fish <= 0:
        return None
    weighted = sum(Decimal(q) * Decimal(str(w)) for q, w in rows)
    avg_g = weighted / Decimal(total_fish)
    return Decimal(total_fish), avg_g


def _biomass_kg_from_stock(fish_count: Decimal, avg_g: Decimal) -> Decimal:
    biomass = BiomassCalculator.calculate_biomass(int(fish_count), float(avg_g))
    return Decimal(str(biomass)).quantize(Decimal("0.01"))


def cycle_stock_snapshot(cycle_id: int) -> dict | None:
    """
    Stock del ciclo en una sola consulta: peces, peso promedio y biomasa (kg).

    Returns:
        ``None`` si el ciclo no tiene lotes con peces.
    """
    stock = cycle_fish_count_and_avg_weight_g(cycle_id)
    if not stock:
        return None
    fish_count, avg_g = stock
    return {
        "current_quantity_total": int(fish_count),
        "current_avg_weight_g": avg_g,
        "current_biomass_kg": _biomass_kg_from_stock(fish_count, avg_g),
    }


def feeding_event_feed_consumed_kg_until(
    event: FeedingEvent,
    *,
    start_date=None,
) -> Decimal:
    """
    Alimento consumido (kg) desde ``start_date`` hasta la fecha del evento.

    Por defecto usa ``cycle.start_date``.
    """
    if start_date is None:
        cycle = Cycle.objects.get(pk=event.cycle_id)
        start_date = cycle.start_date
    return cycle_feed_consumed_kg(
        event.cycle_id,
        start_date=start_date,
        end_date=event.date,
    )


def feed_quantity_to_kg(quantity: Decimal, unit) -> Decimal:
    """Convierte una cantidad de alimento a kilogramos según la unidad de masa."""
    g_per = _mass_grams_per_unit_symbol(unit)
    if g_per is None:
        raise ValueError(
            "No se puede convertir la cantidad de alimento a kg: unidad no soportada "
            f"({getattr(unit, 'symbol', '')})."
        )
    return (quantity * g_per / Decimal("1000")).quantize(Decimal("0.0001"))


def cycle_feed_consumed_kg(
    cycle_id: int,
    *,
    start_date=None,
    end_date=None,
) -> Decimal:
    """
    Suma el alimento real consumido (eventos completados) en un rango de fechas,
    expresado en kg.
    """
    qs = FeedingEvent.objects.filter(
        cycle_id=cycle_id,
        status=FeedingEvent.Status.COMPLETED,
        actual_quantity__isnull=False,
        actual_unit__isnull=False,
    ).select_related("actual_unit")
    if start_date is not None:
        qs = qs.filter(date__gte=start_date)
    if end_date is not None:
        qs = qs.filter(date__lte=end_date)

    total = Decimal("0")
    for ev in qs:
        total += feed_quantity_to_kg(Decimal(str(ev.actual_quantity)), ev.actual_unit)

    from apps.monitoring.models import ProductUsageLog

    food_type_names = [name.casefold() for name in FEED_SCHEDULE_PRODUCT_TYPE_NAMES]
    usage_qs = ProductUsageLog.objects.filter(
        daily_stat__cycle_id=cycle_id,
        daily_stat__deleted_at__isnull=True,
        product__type_product__name__isnull=False,
    ).select_related("unit", "product__type_product", "daily_stat")
    if start_date is not None:
        usage_qs = usage_qs.filter(daily_stat__stat_date__gte=start_date)
    if end_date is not None:
        usage_qs = usage_qs.filter(daily_stat__stat_date__lte=end_date)

    for usage in usage_qs:
        product_type_name = usage.product.type_product.name.casefold()
        if not any(name in product_type_name for name in food_type_names):
            continue
        total += feed_quantity_to_kg(Decimal(str(usage.quantity_used)), usage.unit)

    return total.quantize(Decimal("0.01"))


def planned_feed_quantity_per_ration(
    fish_count: Decimal,
    avg_weight_g: Decimal,
    feeding_rate_percentage: Decimal,
    times_per_day: int,
) -> Decimal:
    """
    Ración planificada por toma (misma unidad que la ración diaria: kg de alimento
    si ``peso_promedio`` está en gramos por pez, coherente con alimento en kg).

    Fórmula de negocio (peso promedio en g por pez):

    - Biomasa = (cantidad de peces × peso promedio) / 1000
    - Relación diaria = (Biomasa × feeding_rate) / 100
    - Ración por toma (quantity) = relación diaria / veces al día
    """
    if times_per_day < 1:
        return Decimal("0").quantize(Decimal("0.000001"))
    biomasa = (fish_count * avg_weight_g) / Decimal("1000")
    relacion_diaria = (biomasa * feeding_rate_percentage) / Decimal("100")
    racion_por_toma = relacion_diaria / Decimal(times_per_day)
    return racion_por_toma.quantize(Decimal("0.000001"))


def create_feeding_events_for_plan(plan: FeedingPlan) -> int:
    schedule = FeedingSchedule.objects.select_related("product").get(
        pk=plan.feeding_schedule_id
    )
    unit_id = schedule.product.unit_id

    stock = cycle_fish_count_and_avg_weight_g(plan.cycle_id)
    if stock is not None:
        fish_count, avg_g = stock
        planned_qty = planned_feed_quantity_per_ration(
            fish_count,
            avg_g,
            Decimal(str(schedule.feeding_rate_percentage)),
            schedule.times_per_day,
        )
    else:
        planned_qty = Decimal("0")

    day_stride = schedule.gap_between_completed_day + 1
    first_ration_time = time(0, 0)

    events: list[FeedingEvent] = []
    ration_number = 1
    day_index = 0
    current = plan.start_date

    while current <= plan.end_date:
        if day_index % day_stride == 0:
            base = datetime.combine(current, first_ration_time)
            for i in range(schedule.times_per_day):
                st = base + timedelta(minutes=i * schedule.gap_between_times_per_day)
                events.append(
                    FeedingEvent(
                        farm_id=plan.farm_id,
                        cycle_id=plan.cycle_id,
                        feeding_plan=plan,
                        date=st.date(),
                        scheduled_time=st.time(),
                        ration_number=ration_number,
                        planned_quantity=planned_qty,
                        planned_unit_id=unit_id,
                        status=FeedingEvent.Status.SCHEDULED,
                    )
                )
                ration_number += 1
        current += timedelta(days=1)
        day_index += 1

    if not events:
        return 0
    audit_bulk_create(FeedingEvent, events)
    return len(events)


def _last_completed_or_skipped_event(old_plan_id: int):
    return (
        FeedingEvent.objects.filter(
            feeding_plan_id=old_plan_id,
            status__in=(
                FeedingEvent.Status.COMPLETED,
                FeedingEvent.Status.SKIPPED,
            ),
        )
        .order_by("-date", "-scheduled_time", "-ration_number")
        .first()
    )


def update_in_progress_feeding_plan(
    *,
    farm_id: int,
    old_plan: FeedingPlan,
    cycle,
    feeding_schedule: FeedingSchedule,
    start_date,
    end_date,
) -> FeedingPlan:
    with transaction.atomic():
        locked_old = FeedingPlan.objects.select_for_update().get(pk=old_plan.pk)
        if locked_old.deleted_at is not None:
            raise ValueError(
                "El plan ya fue archivado. No se puede modificar de este modo."
            )
        if locked_old.farm_id != farm_id:
            raise ValueError("Inconsistencia de granja del plan.")

        last_ev = _last_completed_or_skipped_event(locked_old.pk)
        if last_ev is None:
            raise ValueError(
                "Para actualizar un plan en curso debe existir al menos un evento de "
                "alimentación marcado como completado u omitido. Mantenga los eventos del "
                "plan al día con la operación real (raciones ya ejecutadas o omitidas) y "
                "vuelva a intentar."
            )

        locked_old.end_date = last_ev.date
        locked_old.save(update_fields=["end_date"])

        FeedingEvent.objects.filter(
            feeding_plan_id=locked_old.pk,
            status=FeedingEvent.Status.SCHEDULED,
        ).filter(
            Q(date__gt=last_ev.date)
            | Q(date=last_ev.date, scheduled_time__gt=last_ev.scheduled_time)
            | Q(
                date=last_ev.date,
                scheduled_time=last_ev.scheduled_time,
                ration_number__gt=last_ev.ration_number,
            )
        ).delete()

        new_plan = _create_plan_with_events_locked(
            farm_id=farm_id,
            cycle=cycle,
            feeding_schedule=feeding_schedule,
            start_date=start_date,
            end_date=end_date,
            exclude_plan_ids={locked_old.pk},
        )
    return new_plan


def update_scheduled_feeding_plan(
    *,
    farm_id: int,
    plan: FeedingPlan,
    cycle,
    feeding_schedule: FeedingSchedule,
    start_date,
    end_date,
) -> FeedingPlan:
    with transaction.atomic():
        locked = FeedingPlan.objects.select_for_update().get(pk=plan.pk)
        today = timezone.now().date()
        if not (today < locked.start_date):
            raise ValueError("El plan no está programado (aún en curso o finalizado).")
        if locked.deleted_at is not None:
            raise ValueError("El plan ya fue archivado.")
        if locked.farm_id != farm_id:
            raise ValueError("Inconsistencia de granja del plan.")

        if active_plan_date_overlap(
            cycle_id=cycle.pk,
            start_date=start_date,
            end_date=end_date,
            exclude_plan_ids={locked.pk},
        ):
            raise ValueError(
                "Las fechas se solapan con otro plan vigente del mismo ciclo."
            )

        FeedingEvent.objects.filter(feeding_plan_id=locked.pk).delete()
        locked.cycle_id = cycle.pk
        locked.feeding_schedule_id = feeding_schedule.pk
        locked.start_date = start_date
        locked.end_date = end_date
        locked.save(
            update_fields=[
                "cycle_id",
                "feeding_schedule_id",
                "start_date",
                "end_date",
            ]
        )
        create_feeding_events_for_plan(locked)
    return locked


def _create_plan_with_events_locked(
    *,
    farm_id: int,
    cycle,
    feeding_schedule: FeedingSchedule,
    start_date,
    end_date,
    exclude_plan_ids: set | None = None,
) -> FeedingPlan:
    Cycle.objects.select_for_update().get(pk=cycle.pk)
    if active_plan_date_overlap(
        cycle_id=cycle.pk,
        start_date=start_date,
        end_date=end_date,
        exclude_plan_ids=exclude_plan_ids,
    ):
        raise ValueError(
            "Las fechas se solapan con otro plan vigente del mismo ciclo."
        )
    plan = FeedingPlan.objects.create(
        farm_id=farm_id,
        cycle=cycle,
        feeding_schedule=feeding_schedule,
        start_date=start_date,
        end_date=end_date,
    )
    create_feeding_events_for_plan(plan)
    return plan
