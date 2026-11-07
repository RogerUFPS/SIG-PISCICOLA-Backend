from apps.core.models import Alert
from apps.core.signals import audit_queryset_update
from django.utils import timezone


def resolve_farm(*, farm=None, cycle=None, pond=None):
    """
    Obtiene la granja para una alerta.

    Orden: farm explícito → cycle.farm → pond.farm.
    """
    if farm is not None:
        return farm
    if cycle is not None:
        if getattr(cycle, "farm", None) is not None:
            return cycle.farm
        farm_id = getattr(cycle, "farm_id", None)
        if farm_id:
            from apps.farms.models import Farm

            return Farm.objects.get(pk=farm_id)
    if pond is not None:
        if getattr(pond, "farm", None) is not None:
            return pond.farm
        farm_id = getattr(pond, "farm_id", None)
        if farm_id:
            from apps.farms.models import Farm

            return Farm.objects.get(pk=farm_id)
    return None


def get_active_alerts(
    *, source_type=None, source_id=None, cycle=None, pond=None, farm=None
):
    qs = Alert.objects.filter(is_resolved=False)
    if source_type is not None:
        qs = qs.filter(source_type=source_type)
    if source_id is not None:
        qs = qs.filter(source_id=source_id)
    if cycle is not None:
        qs = qs.filter(cycle=cycle)
    if pond is not None:
        qs = qs.filter(pond=pond)
    if farm is not None:
        qs = qs.filter(farm=farm)
    return qs


def create_alert(
    *,
    farm,
    source_type: str,
    description: str,
    message: str,
    severity: str,
    source_id: int | None = None,
    value: float | None = None,
    threshold: float | None = None,
    pond=None,
    cycle=None,
) -> Alert:
    farm = resolve_farm(farm=farm, cycle=cycle, pond=pond)
    if farm is None:
        raise ValueError(
            "create_alert requiere farm o un cycle/pond del que se pueda inferir la granja."
        )

    existing = get_active_alerts(
        source_type=source_type,
        source_id=source_id,
        farm=farm,
        cycle=cycle,
        pond=pond,
    ).first()

    if existing:
        return existing

    return Alert.objects.create(
        farm=farm,
        pond=pond,
        cycle=cycle,
        source_type=source_type,
        source_id=source_id,
        description=description,
        message=message,
        value=value,
        threshold=threshold,
        severity=severity,
    )


def resolve_alerts(
    *,
    source_type=None,
    source_id=None,
    cycle=None,
    pond=None,
    farm=None,
    resolved_by=None,
) -> None:
    qs = get_active_alerts(
        source_type=source_type,
        source_id=source_id,
        cycle=cycle,
        pond=pond,
        farm=farm,
    )
    audit_queryset_update(
        qs,
        is_resolved=True,
        resolved_at=timezone.now(),
        resolved_by=resolved_by,
    )


def resolve_alerts_for_instance(instance, resolved_by=None):
    if instance is None:
        return

    model_name = instance.__class__.__name__
    if model_name == "Cycle":
        resolve_alerts(cycle=instance, resolved_by=resolved_by)
        return
    if model_name == "Pond":
        resolve_alerts(pond=instance, resolved_by=resolved_by)
        return

    raise ValueError(
        "create_alert_for_instance only soporta instancias Cycle o Pond actualmente."
    )
