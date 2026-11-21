from django.utils import timezone

from apps.batch.models import Batch, BatchSource, BatchTransfer, PondBatch
from apps.cycle.models import Cycle, CyclePondBatch
from apps.feeding.models import FeedingEvent, FeedingPlan
from apps.harvest.models import (
    Harvest,
    HarvestClassification,
    HarvestClassificationSource,
    HarvestSource,
)
from apps.health.models import HealthStat, TreatmentEvent, TreatmentPlan
from apps.monitoring.models import ControlStat, FishEvaluated, ProductUsageLog

from .constants import (
    ALL_MODULES,
    MODULE_BIOMETRY,
    MODULE_FEEDING,
    MODULE_HARVEST,
    MODULE_HEALTH,
    MODULE_LABELS,
    MODULE_SALES,
)
from .indicators import collect_productivity_indicators
from apps.batch.services.traceability import collect_batch_traceability


def _serialize_batch(batch: Batch) -> dict:
    return {
        "id": batch.id,
        "code": batch.code,
        "specie": str(batch.specie),
        "biological_state": batch.get_biological_state_display(),
        "status": batch.get_status_display(),
        "initial_quantity": batch.initial_quantity,
        "min_weight_g": batch.min_weight_g,
        "avg_weight_g": batch.avg_weight_g,
        "max_weight_g": batch.max_weight_g,
        "farm_id": batch.farm_id,
        "farm_name": str(batch.farm),
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }


def _resolve_cycle_context(batch: Batch, cycle_id: int | None) -> dict:
    cpb_qs = CyclePondBatch.objects.filter(
        pond_batch__batch_id=batch.id,
    ).select_related("cycle", "pond_batch__pond")

    if cycle_id is not None:
        cpb_qs = cpb_qs.filter(cycle_id=cycle_id)

    cycle_pond_batches = list(cpb_qs)
    cycle_ids = list({cpb.cycle_id for cpb in cycle_pond_batches})
    cpb_ids = [cpb.id for cpb in cycle_pond_batches]

    cycles = []
    if cycle_ids:
        for cycle in Cycle.objects.filter(id__in=cycle_ids).select_related(
            "pond", "production_plan"
        ):
            cycles.append(
                {
                    "id": cycle.id,
                    "name": cycle.name,
                    "pond": cycle.pond.code,
                    "state": cycle.get_state_display(),
                    "start_date": str(cycle.start_date),
                    "finish_date": str(cycle.finish_date) if cycle.finish_date else None,
                }
            )

    pond_batches = [
        {
            "pond": pb.pond.code,
            "initial_quantity": pb.initial_quantity,
            "current_quantity": pb.current_quantity,
            "start_date": str(pb.start_date),
            "end_date": str(pb.end_date) if pb.end_date else None,
        }
        for pb in PondBatch.objects.filter(batch_id=batch.id).select_related("pond")
    ]

    genealogy = [
        {
            "parent": bs.parent_batch.code,
            "child": bs.child_batch.code,
            "quantity": bs.quantity,
        }
        for bs in BatchSource.objects.filter(
            child_batch_id=batch.id
        ).select_related("parent_batch")
    ] + [
        {
            "parent": bs.parent_batch.code,
            "child": bs.child_batch.code,
            "quantity": bs.quantity,
        }
        for bs in BatchSource.objects.filter(
            parent_batch_id=batch.id
        ).select_related("child_batch")
    ]

    transfers = [
        {
            "from_pond": t.source_pond_batch.pond.code,
            "to_pond": t.to_pond_batch.pond.code,
            "quantity": t.quantity,
            "date": str(t.date),
            "reason": t.reason,
        }
        for t in BatchTransfer.objects.filter(
            source_pond_batch__batch_id=batch.id
        ).select_related(
            "source_pond_batch__pond",
            "to_pond_batch__pond",
        )
    ]

    return {
        "cycle_ids": cycle_ids,
        "cycle_pond_batch_ids": cpb_ids,
        "cycles": cycles,
        "pond_batches": pond_batches,
        "genealogy": genealogy,
        "transfers": transfers,
        "cycle_id_filter": cycle_id,
    }


def _collect_feeding(cycle_ids: list[int]) -> list[dict]:
    if not cycle_ids:
        return []
    records = []
    plans = FeedingPlan.objects.filter(
        cycle_id__in=cycle_ids,
        deleted_at__isnull=True,
    ).select_related("feeding_schedule", "cycle")
    seen_sched = set()
    for plan in plans:
        sched = plan.feeding_schedule
        if sched and sched.id not in seen_sched:
            seen_sched.add(sched.id)
            records.append(
                {
                    "tipo": "cronograma",
                    "nombre": sched.name,
                    "etapa": sched.get_type_display(),
                    "forma_alimento": sched.get_feed_form_display(),
                    "tamano_pellet_mm": str(sched.pellet_size_mm),
                    "porcentaje_alimentacion": str(sched.feeding_rate_percentage),
                    "veces_por_dia": sched.times_per_day,
                    "intervalo_entre_raciones_min": sched.gap_between_times_per_day,
                    "intervalo_entre_jornadas_dias": sched.gap_between_completed_day,
                    "esperado_fca": str(sched.expected_fca),
                    "ganancia_diaria_g": str(sched.expected_daily_gain_g),
                    "peso_min_aceptable_g": str(sched.aceptable_min_weight_g),
                    "peso_max_aceptable_g": str(sched.aceptable_max_weight_g),
                    "comentarios": sched.comments or "",
                }
            )

    # Planes de alimentación por ciclo
    for plan in plans:
        records.append(
            {
                "tipo": "plan",
                "ciclo": plan.cycle.name,
                "programa": plan.feeding_schedule.name,
                "inicio": str(plan.start_date),
                "fin": str(plan.end_date),
            }
        )
    events = (
        FeedingEvent.objects.filter(cycle_id__in=cycle_ids)
        .select_related("cycle", "planned_unit", "actual_unit")
        .order_by("date", "scheduled_time")
    )
    for ev in events:
        unit = (
            ev.actual_unit.symbol
            if ev.actual_unit
            else ev.planned_unit.symbol
        )
        qty = ev.actual_quantity if ev.actual_quantity is not None else ev.planned_quantity
        records.append(
            {
                "tipo": "evento",
                "ciclo": ev.cycle.name,
                "fecha": str(ev.date),
                "hora": str(ev.scheduled_time),
                "racion": ev.ration_number,
                "estado": ev.get_status_display(),
                "cantidad": str(qty),
                "unidad": unit,
            }
        )
    return records


def _collect_biometry(batch_id: int, cycle_ids: list[int]) -> list[dict]:
    records = []
    if cycle_ids:
        for cs in ControlStat.objects.filter(cycle_id__in=cycle_ids).select_related(
            "cycle", "pond"
        ):
            records.append(
                {
                    "tipo": "control",
                    "ciclo": cs.cycle.name,
                    "estanque": cs.pond.code,
                    "fecha": str(cs.control_date),
                    "muestra": cs.sampled_quantity,
                    "vivos": cs.live_quantity,
                    "peso_prom_g": cs.avg_weight_g,
                    "mortalidad_%": cs.mortality_percentage,
                    "biomasa_kg": cs.biomass_kg,
                    "fca": cs.fca,
                }
            )
        for fe in FishEvaluated.objects.filter(
            cycle_id__in=cycle_ids,
            deleted_at__isnull=True,
        ).select_related("cycle", "pond"):
            records.append(
                {
                    "tipo": "evaluacion",
                    "ciclo": fe.cycle.name,
                    "estanque": fe.pond.code,
                    "fecha": str(fe.evaluation_date),
                    "muestra": fe.sampled_quantity,
                    "peso_prom_g": fe.avg_weight_g,
                    "mortalidad": fe.mortality_quantity,
                }
            )
    for pul in ProductUsageLog.objects.filter(batch_id=batch_id).select_related(
        "product", "unit", "daily_stat"
    ):
        records.append(
            {
                "tipo": "uso_producto",
                "producto": pul.product.name,
                "cantidad": pul.quantity_used,
                "unidad": pul.unit.symbol,
                "fecha": str(pul.daily_stat.stat_date),
            }
        )
    return records


def _collect_health(cycle_ids: list[int]) -> list[dict]:
    if not cycle_ids:
        return []
    records = []
    for hs in HealthStat.objects.filter(cycle_id__in=cycle_ids).select_related(
        "cycle", "pond"
    ):
        records.append(
            {
                "tipo": "registro_sanidad",
                "ciclo": hs.cycle.name,
                "estanque": hs.pond.code,
                "fecha": str(hs.date),
                "enfermedad": hs.disease_name,
                "severidad": hs.get_severity_level_display(),
            }
        )
    for tp in TreatmentPlan.objects.filter(
        health_stat__cycle_id__in=cycle_ids
    ).select_related("health_stat", "product"):
        records.append(
            {
                "tipo": "plan_tratamiento",
                "enfermedad": tp.health_stat.disease_name,
                "producto": tp.product.name if tp.product else "—",
                "inicio": str(tp.start_date),
                "fin": str(tp.end_date),
                "estado": tp.get_status_display(),
            }
        )
    for te in TreatmentEvent.objects.filter(cycle_id__in=cycle_ids).select_related(
        "cycle", "treatment_plan"
    ):
        records.append(
            {
                "tipo": "aplicacion",
                "ciclo": te.cycle.name,
                "fecha": str(te.date),
                "hora": str(te.scheduled_time),
                "estado": te.get_status_display(),
                "dosis_plan": str(te.planned_dose),
            }
        )
    return records


def _collect_harvest(cpb_ids: list[int], batch_id: int) -> list[dict]:
    if not cpb_ids:
        return []
    records = []
    harvest_ids_from_sources = set(
        HarvestSource.objects.filter(cycle_pond_batch_id__in=cpb_ids).values_list(
            "harvest_id", flat=True
        )
    )
    harvest_ids_from_class = set(
        HarvestClassificationSource.objects.filter(
            cycle_pond_batch_id__in=cpb_ids
        ).values_list("classification__harvest_id", flat=True)
    )
    harvest_ids = harvest_ids_from_sources | harvest_ids_from_class
    if not harvest_ids:
        return []

    for harvest in Harvest.objects.filter(id__in=harvest_ids).select_related("cycle"):
        records.append(
            {
                "tipo": "cosecha",
                "ciclo": harvest.cycle.name,
                "fecha": str(harvest.date),
                "tipo_cosecha": harvest.get_type_display(),
                "peces": harvest.total_fish_count,
                "peso_total_g": str(harvest.total_weight_g),
            }
        )
        for src in harvest.sources.filter(cycle_pond_batch_id__in=cpb_ids):
            records.append(
                {
                    "tipo": "fuente_cosecha",
                    "cosecha_id": harvest.id,
                    "peces": src.fish_count,
                    "peso_g": str(src.total_weight_g),
                    "trazabilidad": src.get_traceability_type_display(),
                }
            )
        for clf in HarvestClassification.objects.filter(harvest_id=harvest.id):
            records.append(
                {
                    "tipo": "clasificacion",
                    "cosecha_id": harvest.id,
                    "categoria": clf.get_size_category_display(),
                    "peces": clf.fish_count,
                    "peso_g": str(clf.total_weight_g),
                }
            )
    if batch_id:
        from apps.harvest.models import HarvestClassificationDerivation

        for deriv in HarvestClassificationDerivation.objects.filter(
            batch_id=batch_id
        ).select_related("classification"):
            records.append(
                {
                    "tipo": "derivacion_lote",
                    "clasificacion_id": deriv.classification_id,
                    "peces": deriv.fish_count,
                    "peso_g": str(deriv.total_weight_g),
                }
            )
    return records


def _collect_sales() -> list[dict]:
    return []


COLLECTORS = {
    MODULE_FEEDING: lambda ctx, batch: _collect_feeding(ctx["cycle_ids"]),
    MODULE_BIOMETRY: lambda ctx, batch: _collect_biometry(batch.id, ctx["cycle_ids"]),
    MODULE_HEALTH: lambda ctx, batch: _collect_health(ctx["cycle_ids"]),
    MODULE_HARVEST: lambda ctx, batch: _collect_harvest(
        ctx["cycle_pond_batch_ids"], batch.id
    ),
    MODULE_SALES: lambda ctx, batch: _collect_sales(),
}


def collect_production_report_data(
    batch: Batch,
    modules: list[str],
    cycle_id: int | None = None,
    user_display: str = "",
) -> dict:
    selected = [m for m in modules if m in ALL_MODULES]
    ctx = _resolve_cycle_context(batch, cycle_id)

    module_data = {}
    empty_modules = []

    for module_key in selected:
        records = COLLECTORS[module_key](ctx, batch)
        has_data = len(records) > 0
        module_data[module_key] = {
            "label": MODULE_LABELS[module_key],
            "records": records,
            "has_data": has_data,
        }
        if not has_data:
            empty_modules.append(module_key)

    return {
        "batch": _serialize_batch(batch),
        "context": ctx,
        "modules": module_data,
        "empty_modules": empty_modules,
        "empty_module_labels": [MODULE_LABELS[m] for m in empty_modules],
        "selected_modules": selected,
        "productivity_indicators": collect_productivity_indicators(
            batch=batch,
            cycle_ids=ctx["cycle_ids"],
            cycle_id=cycle_id,
        ),
        "generated_at": timezone.now().isoformat(),
        "generated_by": user_display,
        "cycle_id": cycle_id,
        "traceability": collect_batch_traceability(batch),
    }
