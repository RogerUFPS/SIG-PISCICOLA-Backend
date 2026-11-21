from django.utils import timezone

from apps.core.services.alerts import create_alert as create_alert_service
from apps.core.services.alerts import resolve_alerts as resolve_alerts_service

from .models import Alert


def create_alert(
    *,
    farm,
    source_type: str,
    description: str,
    message: str,
    severity: str = Alert.Severity.MEDIUM,
    source_id: int | None = None,
    value: float | None = None,
    threshold: float | None = None,
    pond=None,
    cycle=None,
) -> Alert:
    return create_alert_service(
        farm=farm,
        source_type=source_type,
        description=description,
        message=message,
        severity=severity,
        source_id=source_id,
        value=value,
        threshold=threshold,
        pond=pond,
        cycle=cycle,
    )


def resolve_alert(*, source_type: str, source_id: int, resolved_by=None) -> None:
    resolve_alerts_service(
        source_type=source_type,
        source_id=source_id,
        resolved_by=resolved_by,
    )


def ensure_overdue_events_alerts(farm_id: int) -> None:
    """Lightweight check to create alerts for overdue FeedingEvent and TreatmentEvent.

    This function is safe to call frequently (e.g., from the alerts endpoint) because
    it only scans scheduled events with date <= today for the given farm and uses
    `create_alert` which avoids duplicates.
    """
    from datetime import date

    from apps.feeding.models import FeedingEvent
    from apps.cycle.models import Cycle

    try:
        from apps.health.models import TreatmentEvent
    except Exception:
        TreatmentEvent = None

    today = date.today()

    # Fecha estimada vencida: es informativa y nunca bloquea el ciclo.
    overdue_cycles = Cycle.objects.filter(
        farm_id=farm_id,
        deleted_at__isnull=True,
        state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
        estimated_finish_date__lte=today,
    ).select_related("farm", "pond")
    overdue_cycle_ids = list(overdue_cycles.values_list("id", flat=True))

    for cycle in overdue_cycles:
        create_alert(
            farm=cycle.farm,
            pond=cycle.pond,
            cycle=cycle,
            source_type=Alert.SourceType.CYCLE,
            source_id=cycle.id,
            description=f"Fecha estimada alcanzada para el ciclo {cycle.name}",
            message=(
                f"El ciclo alcanzó su fecha estimada de finalización "
                f"({cycle.estimated_finish_date}) y continúa en proceso."
            ),
            severity=Alert.Severity.MEDIUM,
        )

    stale_cycle_alerts = Alert.objects.filter(
        farm_id=farm_id,
        source_type=Alert.SourceType.CYCLE,
        is_resolved=False,
    )
    if overdue_cycle_ids:
        stale_cycle_alerts = stale_cycle_alerts.exclude(
            source_id__in=overdue_cycle_ids
        )
    from apps.core.signals import audit_queryset_update

    audit_queryset_update(
        stale_cycle_alerts,
        is_resolved=True,
        resolved_at=timezone.now(),
    )

    # Feeding overdue
    feeding_qs = FeedingEvent.objects.filter(
        farm_id=farm_id,
        date__lte=today,
        status=FeedingEvent.Status.SCHEDULED,
    ).select_related("farm", "cycle", "cycle__pond")
    for ev in feeding_qs:
        create_alert(
            farm=ev.farm,
            pond=ev.cycle.pond if ev.cycle_id else None,
            cycle=ev.cycle,
            source_type=Alert.SourceType.FEEDING,
            source_id=ev.id,
            description=f"FeedingEvent pendiente ({ev.id})",
            message=f"Evento programado para {ev.date} no cumplido.",
            severity=Alert.Severity.MEDIUM,
        )

    # Treatment overdue
    if TreatmentEvent is not None:
        treat_qs = TreatmentEvent.objects.filter(
            farm_id=farm_id,
            date__lte=today,
            status=TreatmentEvent.Status.SCHEDULED,
        ).select_related("farm", "cycle", "cycle__pond")
        for ev in treat_qs:
            create_alert(
                farm=ev.farm,
                pond=ev.cycle.pond if ev.cycle_id else None,
                cycle=ev.cycle,
                source_type=Alert.SourceType.HEALTH,
                source_id=ev.id,
                description=f"TreatmentEvent pendiente ({ev.id})",
                message=f"Evento de tratamiento programado para {ev.date} no cumplido.",
                severity=Alert.Severity.MEDIUM,
            )
