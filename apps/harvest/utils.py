# utils.py

from decimal import ROUND_HALF_UP, Decimal

from django.apps import apps
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.batch.services.stock import create_pond_batch
from apps.core.services.alerts import resolve_alerts
from apps.cycle.services.lifecycle import finish_cycle

from .models import (Harvest, HarvestClassification,
                     HarvestClassificationDerivation,
                     HarvestClassificationSource, HarvestSource)
from .validators import WEIGHT_TOLERANCE_G, decimal_weights_equal


def _get_cycle(cycle_id):
    Cycle = apps.get_model("cycle", "Cycle")
    try:
        return Cycle.objects.select_related("farm").get(pk=cycle_id)
    except Cycle.DoesNotExist:
        return None


def _get_cycle_pond_batches_with_stock(cycle, *, for_update=False):
    CyclePondBatch = apps.get_model("cycle", "CyclePondBatch")
    PondBatch = apps.get_model("batch", "PondBatch")

    cycle_pond_batches = list(
        CyclePondBatch.objects.filter(
            cycle=cycle,
            pond_batch__end_date__isnull=True,
            pond_batch__current_quantity__gt=0,
        ).select_related("pond_batch", "pond_batch__batch")
    )
    if not cycle_pond_batches:
        return []

    if not for_update:
        return cycle_pond_batches

    pond_batch_ids = [cpb.pond_batch_id for cpb in cycle_pond_batches]
    locked_pond_batches = {
        pb.id: pb
        for pb in PondBatch.objects.filter(id__in=pond_batch_ids).select_for_update()
    }

    for cpb in cycle_pond_batches:
        cpb.pond_batch = locked_pond_batches[cpb.pond_batch_id]

    return cycle_pond_batches


def _get_available_quantity(cycle):
    cycle_pond_batches = _get_cycle_pond_batches_with_stock(cycle)
    return sum(cpb.pond_batch.current_quantity for cpb in cycle_pond_batches)


def _distribute_integer_proportionally(total, weights):
    if not weights:
        return []
    if total <= 0:
        return [0] * len(weights)

    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [0] * len(weights)

    allocations = []
    remaining = total
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            allocations.append(remaining)
        else:
            share = int(total * weight / weight_sum)
            allocations.append(share)
            remaining -= share
    return allocations


def _distribute_decimal_proportionally(total, weights):
    if not weights:
        return []

    total = Decimal(total)
    if total <= 0:
        return [Decimal("0")] * len(weights)

    weight_sum = sum(Decimal(w) for w in weights)
    if weight_sum <= 0:
        return [Decimal("0")] * len(weights)

    allocations = []
    remaining = total
    quantize = Decimal("1")
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            allocations.append(remaining.quantize(quantize, rounding=ROUND_HALF_UP))
        else:
            share = (total * Decimal(weight) / weight_sum).quantize(
                quantize, rounding=ROUND_HALF_UP
            )
            allocations.append(share)
            remaining -= share
    return allocations


def _build_harvest_allocations(cycle_pond_batches, total_fish_count, total_weight_g):
    weights = [cpb.pond_batch.current_quantity for cpb in cycle_pond_batches]
    available = sum(weights)

    if available <= 0:
        raise ValueError("No hay biomasa disponible en los lotes del ciclo.")

    if total_fish_count > available:
        raise ValueError(
            f"La cantidad cosechada ({total_fish_count}) excede la disponible ({available})."
        )

    fish_allocations = _distribute_integer_proportionally(total_fish_count, weights)
    weight_allocations = _distribute_decimal_proportionally(total_weight_g, weights)

    allocations = []
    for cpb, fish_count, weight_g in zip(
        cycle_pond_batches, fish_allocations, weight_allocations
    ):
        if fish_count <= 0:
            continue
        if fish_count > cpb.pond_batch.current_quantity:
            raise ValueError(
                f"La asignación ({fish_count}) excede el stock del lote "
                f"{cpb.pond_batch.batch.code} ({cpb.pond_batch.current_quantity})."
            )
        allocations.append(
            {
                "cycle_pond_batch": cpb,
                "fish_count": fish_count,
                "total_weight_g": weight_g,
            }
        )

    if not allocations:
        raise ValueError("No se pudo distribuir la cosecha entre los lotes del ciclo.")

    allocated_fish = sum(item["fish_count"] for item in allocations)
    if allocated_fish != total_fish_count:
        raise ValueError(
            f"Inconsistencia en la distribución: asignados {allocated_fish}, "
            f"esperados {total_fish_count}."
        )

    return allocations


def _reduce_pond_batch_quantity(pond_batch, quantity):
    Batch = apps.get_model("batch", "Batch")

    if quantity > pond_batch.current_quantity:
        raise ValueError(
            f"La cantidad cosechada ({quantity}) excede la disponible "
            f"({pond_batch.current_quantity})."
        )

    pond_batch.current_quantity -= quantity
    update_fields = ["current_quantity"]

    if pond_batch.current_quantity == 0:
        pond_batch.end_date = timezone.now().date()
        update_fields.append("end_date")

        # ✓ NUEVA LÓGICA: Cambiar batch a CONSUMED cuando se vende completamente
        batch = pond_batch.batch
        if batch.status == Batch.Status.ACTIVE:
            batch.status = Batch.Status.CONSUMED
            batch.save(update_fields=["status"])

    pond_batch.save(update_fields=update_fields)
    return pond_batch


def _create_harvest_sources(harvest, allocations):
    HarvestSource.objects.bulk_create(
        [
            HarvestSource(
                harvest=harvest,
                cycle_pond_batch=item["cycle_pond_batch"],
                fish_count=item["fish_count"],
                total_weight_g=item["total_weight_g"],
                traceability_type=HarvestSource.TraceabilityType.PROPORTIONAL,
            )
            for item in allocations
        ]
    )


def _is_cycle_fully_harvested(cycle):
    CyclePondBatch = apps.get_model("cycle", "CyclePondBatch")
    return not CyclePondBatch.objects.filter(
        cycle=cycle,
        pond_batch__end_date__isnull=True,
        pond_batch__current_quantity__gt=0,
    ).exists()


def _validate_harvest(cycle, harvest_type, total_fish_count):
    Cycle = apps.get_model("cycle", "Cycle")
    errors = {}

    blocked_states = [
        Cycle.State.FINISHED,
        Cycle.State.CANCELLED,
        Cycle.State.PAUSED,
    ]
    if cycle.state in blocked_states:
        errors["cycle"] = f"No se puede cosechar un ciclo en estado '{cycle.state}'."

    if harvest_type == Harvest.Type.TOTAL:
        already_total = Harvest.objects.filter(
            cycle=cycle,
            type=Harvest.Type.TOTAL,
        ).exists()
        if already_total:
            errors["type"] = "Ya existe una cosecha Total para este ciclo."

    return errors


def _check_active_treatment(cycle):
    try:
        TreatmentPlan = apps.get_model("health", "TreatmentPlan")
    except LookupError:
        return False
    return TreatmentPlan.objects.filter(
        health_stat__cycle=cycle,
        status=TreatmentPlan.Status.IN_PROGRESS,
    ).exists()


def _cancel_scheduled_events(cycle):
    try:
        FeedingEvent = apps.get_model("feeding", "FeedingEvent")
    except LookupError:
        FeedingEvent = None

    if FeedingEvent is not None:
        FeedingEvent.objects.filter(
            cycle=cycle,
            status=FeedingEvent.Status.SCHEDULED,
        ).delete()

    try:
        TreatmentEvent = apps.get_model("health", "TreatmentEvent")
    except LookupError:
        TreatmentEvent = None

    if TreatmentEvent is not None:
        TreatmentEvent.objects.filter(
            cycle=cycle,
            status=TreatmentEvent.Status.SCHEDULED,
        ).delete()


def _resolve_cycle_alerts(cycle):
    resolve_alerts(cycle=cycle)


def _validate_cycle_finish_date(cycle, finish_date) -> None:
    if finish_date < cycle.start_date:
        raise ValueError(
            f"La fecha de fin ({finish_date}) no puede ser anterior al inicio del ciclo "
            f"({cycle.start_date})."
        )


def finish_cycle_from_harvest(cycle, finish_date) -> None:
    finish_cycle(cycle, finish_date)


def get_classification_derived_fish_count(classification_id: int) -> int:
    total = HarvestClassificationDerivation.objects.filter(
        classification_id=classification_id,
    ).aggregate(total=Sum("fish_count"))["total"]
    return total or 0


def get_classification_available_fish_count(
    classification: HarvestClassification,
) -> int:
    derived = get_classification_derived_fish_count(classification.id)
    SaleDetail = apps.get_model("sales", "SaleDetail")
    sold = (
        SaleDetail.objects.filter(
            harvest_classification=classification,
            fish_count__isnull=False,
        ).aggregate(total=Sum("fish_count"))["total"]
        or 0
    )

    return max(classification.fish_count - derived - sold, 0)


def get_classification_available_weight_g(
    classification: HarvestClassification,
    exclude_detail_id: int | None = None,
) -> Decimal:
    derived_weight: Decimal = HarvestClassificationDerivation.objects.filter(
        classification=classification
    ).aggregate(total=Sum("total_weight_g"))["total"] or Decimal("0")

    SaleDetail = apps.get_model("sales", "SaleDetail")
    sold_qs = SaleDetail.objects.filter(harvest_classification=classification)
    if exclude_detail_id is not None:
        sold_qs = sold_qs.exclude(pk=exclude_detail_id)

    sold_weight = sold_qs.aggregate(total=Sum("quantity_g"))["total"] or Decimal("0")

    total_weight = Decimal(str(classification.total_weight_g))
    available = total_weight - derived_weight - Decimal(sold_weight)
    return max(available, Decimal("0"))


def _weight_for_partial_derivation(classification, fish_count: int) -> Decimal:
    if classification.fish_count <= 0:
        return Decimal("0")
    ratio = Decimal(fish_count) / Decimal(classification.fish_count)
    weight = Decimal(classification.total_weight_g) * ratio
    return weight.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _get_harvest_source_map(harvest_id: int) -> dict[int, HarvestSource]:
    return {
        source.cycle_pond_batch_id: source
        for source in HarvestSource.objects.filter(harvest_id=harvest_id)
    }


def validate_exact_classification_sources(
    harvest: Harvest,
    classifications_data: list[dict],
) -> None:
    CyclePondBatch = apps.get_model("cycle", "CyclePondBatch")

    cycle_batch_ids = set(
        CyclePondBatch.objects.filter(cycle=harvest.cycle).values_list("id", flat=True)
    )
    harvest_source_totals: dict[int, int] = {}

    for classification_data in classifications_data:
        sources = classification_data.get("sources") or []
        if not sources:
            raise ValueError(
                f"La clasificación {classification_data.get('size_category')} "
                "requiere sources en modo exact."
            )

        class_fish = classification_data["fish_count"]
        class_weight = Decimal(classification_data["total_weight_g"])
        source_fish = 0
        source_weight = Decimal("0")

        seen_batches = set()
        for source in sources:
            cpb_id = source["cycle_pond_batch_id"]
            if cpb_id not in cycle_batch_ids:
                raise ValueError(
                    f"CyclePondBatch {cpb_id} no pertenece al ciclo de la cosecha."
                )
            if cpb_id in seen_batches:
                raise ValueError(
                    f"CyclePondBatch {cpb_id} duplicado en la clasificación "
                    f"{classification_data.get('size_category')}."
                )
            seen_batches.add(cpb_id)

            fish = source["fish_count"]
            weight = Decimal(source["total_weight_g"])
            if fish <= 0:
                raise ValueError("fish_count de cada source debe ser mayor a 0.")

            source_fish += fish
            source_weight += weight
            harvest_source_totals[cpb_id] = harvest_source_totals.get(cpb_id, 0) + fish

        if source_fish != class_fish:
            raise ValueError(
                f"La suma de sources ({source_fish}) debe igualar fish_count "
                f"({class_fish}) de la clasificación "
                f"{classification_data.get('size_category')}."
            )
        if not decimal_weights_equal(source_weight, class_weight):
            raise ValueError(
                f"La suma de total_weight_g en sources ({source_weight} g) debe igualar "
                f"el de la clasificación {classification_data.get('size_category')} "
                f"({class_weight} g) con tolerancia de {WEIGHT_TOLERANCE_G} g."
            )


def validate_classification_sources_against_harvest(
    harvest_id: int,
    harvest_source_totals: dict[int, int],
) -> None:
    harvest_sources = _get_harvest_source_map(harvest_id)
    for cpb_id, attributed in harvest_source_totals.items():
        harvest_source = harvest_sources.get(cpb_id)
        if not harvest_source:
            raise ValueError(
                f"CyclePondBatch {cpb_id} no participó en la cosecha (HarvestSource)."
            )
        if attributed > harvest_source.fish_count:
            raise ValueError(
                f"La clasificación atribuye {attributed} peces al lote {cpb_id}, "
                f"pero la cosecha solo registró {harvest_source.fish_count}."
            )

    for cpb_id, harvest_source in harvest_sources.items():
        attributed = harvest_source_totals.get(cpb_id, 0)
        if attributed != harvest_source.fish_count:
            raise ValueError(
                f"El lote {cpb_id} aportó {harvest_source.fish_count} peces a la cosecha, "
                f"pero las clasificaciones suman {attributed}."
            )


def _create_classification_sources_proportional(harvest: Harvest) -> None:
    harvest_sources = list(HarvestSource.objects.filter(harvest=harvest).order_by("id"))
    if not harvest_sources:
        return

    parent_weights = [source.fish_count for source in harvest_sources]
    records = []

    for classification in harvest.classifications.all():
        fish_allocations = _distribute_integer_proportionally(
            classification.fish_count,
            parent_weights,
        )
        weight_allocations = _distribute_decimal_proportionally(
            classification.total_weight_g,
            parent_weights,
        )
        for source, fish_count, weight_g in zip(
            harvest_sources, fish_allocations, weight_allocations
        ):
            if fish_count <= 0:
                continue
            records.append(
                HarvestClassificationSource(
                    classification=classification,
                    cycle_pond_batch=source.cycle_pond_batch,
                    fish_count=fish_count,
                    total_weight_g=weight_g,
                    traceability_type=HarvestClassificationSource.TraceabilityType.PROPORTIONAL,
                )
            )

    if records:
        HarvestClassificationSource.objects.bulk_create(records)


def _create_classification_sources_exact(
    harvest: Harvest,
    classifications_data: list[dict],
) -> None:
    classification_by_category = {
        c.size_category: c for c in harvest.classifications.all()
    }
    records = []

    for classification_data in classifications_data:
        classification = classification_by_category[
            classification_data["size_category"]
        ]
        for source in classification_data.get("sources") or []:
            records.append(
                HarvestClassificationSource(
                    classification=classification,
                    cycle_pond_batch_id=source["cycle_pond_batch_id"],
                    fish_count=source["fish_count"],
                    total_weight_g=source["total_weight_g"],
                    traceability_type=HarvestClassificationSource.TraceabilityType.EXACT,
                )
            )

    if records:
        HarvestClassificationSource.objects.bulk_create(records)


def build_classification_sources(
    harvest: Harvest,
    classifications_data: list[dict],
) -> None:
    if harvest.traceability_mode == Harvest.TraceabilityMode.EXACT:
        harvest_source_totals: dict[int, int] = {}
        for classification_data in classifications_data:
            for source in classification_data.get("sources") or []:
                cpb_id = source["cycle_pond_batch_id"]
                harvest_source_totals[cpb_id] = (
                    harvest_source_totals.get(cpb_id, 0) + source["fish_count"]
                )
        validate_classification_sources_against_harvest(
            harvest.id,
            harvest_source_totals,
        )
        _create_classification_sources_exact(harvest, classifications_data)
    else:
        _create_classification_sources_proportional(harvest)


@transaction.atomic
def confirm_harvest(
    harvest: Harvest,
    classifications_data: list[dict] | None = None,
) -> None:
    cycle = harvest.cycle
    cycle_pond_batches = _get_cycle_pond_batches_with_stock(cycle, for_update=True)

    if not cycle_pond_batches:
        raise ValueError("No hay lotes activos con stock en este ciclo.")

    available_locked = sum(
        cpb.pond_batch.current_quantity for cpb in cycle_pond_batches
    )
    if harvest.total_fish_count > available_locked:
        raise ValueError(
            f"La cantidad a cosechar ({harvest.total_fish_count}) excede "
            f"la disponible ({available_locked})."
        )

    allocations = _build_harvest_allocations(
        cycle_pond_batches,
        harvest.total_fish_count,
        harvest.total_weight_g,
    )

    for item in allocations:
        _reduce_pond_batch_quantity(
            item["cycle_pond_batch"].pond_batch,
            item["fish_count"],
        )

    _create_harvest_sources(harvest, allocations)

    if classifications_data is not None:
        build_classification_sources(harvest, classifications_data)

    should_close = _is_cycle_fully_harvested(cycle)
    if should_close:
        finish_cycle(cycle, harvest.date)


def _create_batch_sources_for_derivation(
    classification: HarvestClassification,
    child_batch,
    fish_count: int,
):
    classification_sources = list(
        HarvestClassificationSource.objects.filter(classification=classification)
        .select_related("cycle_pond_batch__pond_batch__batch")
        .order_by("id")
    )

    if classification_sources:
        weights = [source.fish_count for source in classification_sources]
        quantities = _distribute_integer_proportionally(fish_count, weights)
        for source, quantity in zip(classification_sources, quantities):
            if quantity <= 0:
                continue
            parent_batch = source.cycle_pond_batch.pond_batch.batch
            _upsert_batch_source(parent_batch, child_batch, quantity)
        return

    harvest_sources = list(
        HarvestSource.objects.filter(harvest=classification.harvest)
        .select_related("cycle_pond_batch__pond_batch__batch")
        .order_by("id")
    )
    if not harvest_sources:
        raise ValueError(
            "No hay fuentes de trazabilidad para esta cosecha. "
            "No se pueden vincular lotes padre."
        )

    weights = [source.fish_count for source in harvest_sources]
    quantities = _distribute_integer_proportionally(fish_count, weights)
    for source, quantity in zip(harvest_sources, quantities):
        if quantity <= 0:
            continue
        parent_batch = source.cycle_pond_batch.pond_batch.batch
        _upsert_batch_source(parent_batch, child_batch, quantity)


def _upsert_batch_source(parent_batch, child_batch, quantity: int):
    BatchSource = apps.get_model("batch", "BatchSource")
    existing = BatchSource.objects.filter(
        parent_batch=parent_batch,
        child_batch=child_batch,
    ).first()
    if existing:
        existing.quantity += quantity
        existing.save(update_fields=["quantity"])
    else:
        BatchSource.objects.create(
            parent_batch=parent_batch,
            child_batch=child_batch,
            quantity=quantity,
        )


@transaction.atomic
def create_batch_from_classification(
    classification: HarvestClassification,
    specie_id: int | None,
    biological_state: str,
    min_weight_g: float,
    avg_weight_g: float,
    max_weight_g: float,
    pond_id: int,
    fish_count: int | None = None,
    comments: str = "",
    created_by=None,
) -> object:
    Batch = apps.get_model("batch", "Batch")
    PondBatch = apps.get_model("batch", "PondBatch")

    locked = HarvestClassification.objects.select_for_update().get(pk=classification.pk)
    classification = locked

    if fish_count is None:
        fish_count = get_classification_available_fish_count(classification)

    if fish_count <= 0:
        raise ValueError("fish_count debe ser mayor a 0.")

    available = get_classification_available_fish_count(classification)
    if fish_count > available:
        raise ValueError(
            f"La cantidad a derivar ({fish_count}) excede la disponible "
            f"en la clasificación ({available})."
        )

    if specie_id is None:
        specie_id = infer_specie_id_for_classification(classification)

    farm = classification.farm
    timestamp = int(timezone.now().timestamp())
    code = f"BATCH-{farm.id}-{timestamp}"
    while Batch.objects.filter(code=code, farm=farm).exists():
        timestamp += 1
        code = f"BATCH-{farm.id}-{timestamp}"

    derivation_weight = _weight_for_partial_derivation(classification, fish_count)

    batch = Batch.objects.create(
        farm=farm,
        specie_id=specie_id,
        origin_type=Batch.OriginType.HARVEST_CLASSIFICATION,
        origin_id=classification.id,
        code=code,
        biological_state=biological_state,
        status=Batch.Status.ACTIVE,
        initial_quantity=fish_count,
        min_weight_g=min_weight_g,
        avg_weight_g=avg_weight_g,
        max_weight_g=max_weight_g,
        comments=comments,
    )

    Pond = apps.get_model("ponds", "Pond")
    pond = Pond.objects.get(pk=pond_id)

    create_pond_batch(
        pond=pond,
        batch=batch,
        initial_quantity=fish_count,
        start_date=timezone.now().date(),
    )

    _create_batch_sources_for_derivation(classification, batch, fish_count)

    HarvestClassificationDerivation.objects.create(
        classification=classification,
        batch=batch,
        fish_count=fish_count,
        total_weight_g=derivation_weight,
        pond_id=pond_id,
        created_by=created_by or classification.created_by,
    )

    return batch


def get_cycle_weights(cycle) -> dict:
    ControlStat = apps.get_model("monitoring", "ControlStat")

    last_control = (
        ControlStat.objects.filter(
            cycle=cycle,
            deleted_at__isnull=True,
        )
        .order_by("-control_date")
        .first()
    )

    if not last_control:
        return {
            "min_weight_g": 0.0,
            "avg_weight_g": 0.0,
            "max_weight_g": 0.0,
        }

    return {
        "min_weight_g": last_control.min_weight_g,
        "avg_weight_g": last_control.avg_weight_g,
        "max_weight_g": last_control.max_weight_g,
    }


def get_last_control_stat_for_cycle(cycle):
    ControlStat = apps.get_model("monitoring", "ControlStat")
    return (
        ControlStat.objects.filter(
            cycle=cycle,
            deleted_at__isnull=True,
        )
        .order_by("-control_date")
        .first()
    )


def infer_total_fish_count(cycle) -> int:
    available = _get_available_quantity(cycle)
    if available <= 0:
        raise ValueError("No hay stock vivo disponible en los lotes activos del ciclo.")
    return available


def infer_total_weight_g(cycle, total_fish_count: int) -> Decimal:
    weights = get_cycle_weights(cycle)
    avg_weight_g = Decimal(str(weights["avg_weight_g"]))
    total = Decimal(total_fish_count) * avg_weight_g
    return total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def infer_harvest_type(cycle, total_fish_count: int) -> str:
    available = _get_available_quantity(cycle)
    if total_fish_count >= available:
        return Harvest.Type.TOTAL
    return Harvest.Type.PARTIAL


def _collect_parent_biological_states(classification) -> list[str]:
    states = []

    class_sources = HarvestClassificationSource.objects.filter(
        classification=classification,
    ).select_related("cycle_pond_batch__pond_batch__batch")
    for source in class_sources:
        if source.fish_count <= 0:
            continue
        states.append(source.cycle_pond_batch.pond_batch.batch.biological_state)

    if states:
        return states

    harvest_sources = HarvestSource.objects.filter(
        harvest_id=classification.harvest_id,
    ).select_related("cycle_pond_batch__pond_batch__batch")
    for source in harvest_sources:
        if source.fish_count <= 0:
            continue
        states.append(source.cycle_pond_batch.pond_batch.batch.biological_state)

    return states


def infer_specie_id_for_classification(classification) -> int:
    return classification.harvest.cycle.specie_id


def infer_biological_state_for_classification(classification) -> str | None:
    states = _collect_parent_biological_states(classification)
    if not states:
        return None
    unique = set(states)
    if len(unique) == 1:
        return unique.pop()
    return None
