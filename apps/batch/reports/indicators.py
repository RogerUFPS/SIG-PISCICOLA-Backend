from django.db.models import Sum

from apps.batch.models import Batch
from apps.cycle.models import Cycle, CyclePondBatch
from apps.monitoring.models import ControlStat, FishEvaluated
from apps.monitoring.services import BiomassCalculator
from apps.species.models import SpecieFeedingReference, SpecieProductionReference


def _format_range(value_min, value_max, unit="") -> str:
    if value_min is None or value_max is None:
        return ""
    return f"{value_min:.2f}{unit} - {value_max:.2f}{unit}" if unit else f"{value_min:.2f} - {value_max:.2f}"


def _build_indicator(
    name: str,
    value: str,
    status: str,
    classification: str,
    recommendation: str,
    notes: str,
) -> dict:
    return {
        "name": name,
        "value": value,
        "status": status,
        "classification": classification,
        "recommendation": recommendation,
        "notes": notes,
    }


def _get_feeding_reference(batch: Batch) -> SpecieFeedingReference | None:
    return SpecieFeedingReference.objects.filter(
        specie=batch.specie,
        stage=batch.biological_state,
    ).first()


def _get_production_reference(batch: Batch, cycle_id: int | None) -> SpecieProductionReference | None:
    if cycle_id is None:
        return None
    cycle = Cycle.objects.select_related("production_plan").filter(id=cycle_id).first()
    if not cycle or not cycle.production_plan:
        return None
    return SpecieProductionReference.objects.filter(
        specie=batch.specie,
        type=cycle.production_plan.type,
    ).first()


def _get_initial_stock(batch: Batch, cycle_id: int | None) -> int:
    if cycle_id is None:
        return batch.initial_quantity or 0
    quantities = (
        CyclePondBatch.objects.filter(
            cycle_id=cycle_id,
            pond_batch__batch=batch,
        )
        .aggregate(total=Sum("quantity"))
        .get("total")
    )
    if quantities:
        return int(quantities)
    return batch.initial_quantity or 0


def calculate_fca(batch: Batch, cycle_ids: list[int]) -> dict:
    control_stats = ControlStat.objects.filter(
        cycle_id__in=cycle_ids,
        deleted_at__isnull=True,
    ).order_by("control_date")

    if control_stats.count() < 2:
        return _build_indicator(
            name="FCA",
            value="N/A",
            status="No calculable",
            classification="Datos de biometría insuficientes",
            recommendation=(
                "Se requieren al menos dos muestreos biométricos para estimar el FCA. "
                "Verifique los registros de ControlStat y de alimentación del ciclo."
            ),
            notes="Sin datos suficientes para este indicador.",
        )

    latest_control = control_stats.last()
    if latest_control is None:
        return _build_indicator(
            name="FCA",
            value="N/A",
            status="No calculable",
            classification="Cálculo de FCA no disponible",
            recommendation=(
                "No se encontró un valor de FCA calculado en el último ControlStat. "
                "Asegure que los muestreos biométricos y el consumo de alimento estén correctamente registrados."
            ),
            notes="Sin datos suficientes para este indicador.",
        )

    fca = latest_control.fca
    if fca is None and latest_control.biomass_gain_kg:
        from apps.feeding.utils import cycle_feed_consumed_kg

        feed_kg = sum(
            (
                cycle_feed_consumed_kg(cycle_id=cycle_id)
                for cycle_id in cycle_ids
            ),
            0,
        )
        fca = BiomassCalculator.calculate_fca(
            float(feed_kg), latest_control.biomass_gain_kg
        )

    if fca is None:
        return _build_indicator(
            name="FCA",
            value="N/A",
            status="No calculable",
            classification="Cálculo de FCA no disponible",
            recommendation=(
                "Registre suministros efectivos y controles biométricos con ganancia "
                "de biomasa para calcular el FCA."
            ),
            notes="Sin datos suficientes para este indicador.",
        )
    classification = "Sin referencia técnica disponible"
    recommendation = "Revise las referencias de alimentación para esta especie y etapa."
    ref = _get_feeding_reference(batch)
    if ref is not None:
        lower = float(ref.reference_fca_min)
        upper = float(ref.reference_fca_max)
        if fca < lower:
            classification = "FCA por debajo del rango esperado"
            recommendation = (
                "El consumo de alimento es bajo respecto a la ganancia de biomasa. "
                "Confirme la exactitud de la captura de datos y la calidad del alimento."
            )
        elif fca > upper:
            classification = "FCA por encima del rango esperado"
            recommendation = (
                "La conversión alimenticia es ineficiente. "
                "Revise la salud del cultivo, la calidad del alimento y los protocolos de alimentación."
            )
        else:
            classification = "FCA dentro del rango técnico esperado"
            recommendation = (
                "El ciclo tiene una conversión alimenticia adecuada. "
                "Mantenga las prácticas actuales y continúe monitoreando."
            )

    return _build_indicator(
        name="FCA",
        value=f"{fca:.2f}",
        status="Calculado",
        classification=classification,
        recommendation=recommendation,
        notes=(
            f"Referencia técnica: {_format_range(lower, upper)}" if ref is not None else ""
        ),
    )


def calculate_mortality(batch: Batch, cycle_id: int | None, cycle_ids: list[int]) -> dict:
    initial_stock = _get_initial_stock(batch, cycle_id)
    evaluations = FishEvaluated.objects.filter(
        cycle_id__in=cycle_ids,
        deleted_at__isnull=True,
    )

    if initial_stock <= 0 or not evaluations.exists():
        return _build_indicator(
            name="Mortalidad acumulada",
            value="N/A",
            status="No calculable",
            classification="Datos de siembra o mortalidad insuficientes",
            recommendation=(
                "Se requiere el dato de siembra inicial y registros de mortalidad para calcular este indicador."
            ),
            notes="Sin datos suficientes para este indicador.",
        )

    total_mortality = evaluations.aggregate(total=Sum("mortality_quantity"))["total"] or 0
    mortality_rate = (total_mortality / initial_stock) * 100 if initial_stock > 0 else 0.0
    production_ref = _get_production_reference(batch, cycle_id)
    classification = "Sin referencia técnica disponible"
    recommendation = "Monitoree las condiciones sanitarias y registre correctamente las mortalidades."

    expected_rate = None
    if cycle_id is not None:
        cycle = Cycle.objects.select_related("production_plan").filter(id=cycle_id).first()
        if cycle and cycle.production_plan:
            expected_rate = float(cycle.production_plan.expected_mortality_rate)
    if expected_rate is None and production_ref is not None:
        expected_rate = float(production_ref.reference_mortality_rate_max)

    if expected_rate is not None:
        if mortality_rate <= expected_rate:
            classification = "Mortalidad dentro del rango esperado"
            recommendation = (
                "El ciclo está cumpliendo las expectativas de mortalidad. "
                "Mantenga las medidas de bioseguridad y de manejo actual."
            )
        else:
            classification = "Mortalidad por encima del rango esperado"
            recommendation = (
                "La mortalidad acumulada está por encima de lo esperado. "
                "Investigue causas de estrés, sanidad y condiciones ambientales."
            )
    else:
        classification = "Referencia de mortalidad no disponible"

    notes = []
    if production_ref is not None:
        notes.append(
            f"Referencia técnica: {production_ref.reference_mortality_rate_min:.4f}% - {production_ref.reference_mortality_rate_max:.4f}%"
        )
    if initial_stock > 0:
        notes.append(f"Siembra inicial considerada: {initial_stock}")

    return _build_indicator(
        name="Mortalidad acumulada",
        value=f"{mortality_rate:.2f}%",
        status="Calculado",
        classification=classification,
        recommendation=recommendation,
        notes=" | ".join(notes),
    )


def calculate_gdp(batch: Batch, cycle_ids: list[int]) -> dict:
    control_stats = ControlStat.objects.filter(
        cycle_id__in=cycle_ids,
        deleted_at__isnull=True,
    ).order_by("control_date")

    if control_stats.count() < 2:
        return _build_indicator(
            name="GDP",
            value="N/A",
            status="No calculable",
            classification="Menos de dos muestreos biométricos",
            recommendation=(
                "Se requieren al menos dos registros de ControlStat para calcular la ganancia diaria de peso."
            ),
            notes="Sin datos suficientes para este indicador.",
        )

    earliest = control_stats.first()
    latest = control_stats.last()
    days = (latest.control_date - earliest.control_date).days
    if days <= 0:
        return _build_indicator(
            name="GDP",
            value="N/A",
            status="No calculable",
            classification="Periodo de muestreo inválido",
            recommendation=(
                "Los muestreos biométricos deben tener fechas distintas para calcular el GDP."
            ),
            notes="Sin datos suficientes para este indicador.",
        )

    gain_per_day = (latest.avg_weight_g - earliest.avg_weight_g) / days
    ref = _get_feeding_reference(batch)
    classification = "Sin referencia técnica disponible"
    recommendation = "Monitoree el crecimiento y compare con las referencias de especie."
    if ref is not None:
        lower = float(ref.reference_daily_gain_g_min)
        upper = float(ref.reference_daily_gain_g_max)
        if gain_per_day < lower:
            classification = "GDP por debajo del rango esperado"
            recommendation = (
                "La ganancia diaria de peso es baja. Revise densidades, alimentación y condiciones ambientales."
            )
        elif gain_per_day > upper:
            classification = "GDP por encima del rango esperado"
            recommendation = (
                "La ganancia diaria de peso es elevada. Mantenga las prácticas actuales y verifique la conservación de la biomasa."
            )
        else:
            classification = "GDP dentro del rango técnico esperado"
            recommendation = (
                "El crecimiento diario es adecuado. Continúe con el sistema de alimentación y seguimiento actual."
            )

    notes = (
        f"Referencia técnica: {_format_range(float(ref.reference_daily_gain_g_min), float(ref.reference_daily_gain_g_max), ' g/día')}"
        if ref is not None
        else ""
    )

    return _build_indicator(
        name="GDP",
        value=f"{gain_per_day:.2f} g/día",
        status="Calculado",
        classification=classification,
        recommendation=recommendation,
        notes=notes,
    )


def collect_productivity_indicators(
    batch: Batch,
    cycle_ids: list[int],
    cycle_id: int | None,
) -> list[dict]:
    return [
        calculate_fca(batch, cycle_ids),
        calculate_mortality(batch, cycle_id, cycle_ids),
        calculate_gdp(batch, cycle_ids),
    ]
