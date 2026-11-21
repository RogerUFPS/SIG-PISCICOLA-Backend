from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.core.models import Alert
from apps.core.utils import create_alert, resolve_alert

from .models import HealthStat, TreatmentEvent


@receiver(
    post_save,
    sender=HealthStat,
    dispatch_uid="health_stat_disease_alert_v1",
)
def health_stat_disease_alert(sender, instance: HealthStat, created, **kwargs):
    if not created:
        return

    create_alert(
        farm=instance.farm,
        pond=instance.pond,
        cycle=instance.cycle,
        source_type=Alert.SourceType.HEALTH_STAT,
        source_id=instance.id,
        description=f"Diagnóstico sanitario: {instance.disease_name}",
        message=(
            f"Se registró {instance.disease_name} en el ciclo "
            f"{instance.cycle.name}, estanque {instance.pond.name}, "
            f"con fecha {instance.date}."
        ),
        severity=instance.severity_level,
    )


@receiver(
    post_save,
    sender=TreatmentEvent,
    dispatch_uid="treatment_event_alert_v1",
)
def treatment_event_alert(sender, instance: TreatmentEvent, created, **kwargs):
    today = timezone.now().date()
    if instance.status == TreatmentEvent.Status.SCHEDULED and instance.date <= today:
        create_alert(
            farm=instance.farm,
            pond=getattr(instance, "pond", None),
            cycle=instance.cycle,
            source_type=Alert.SourceType.HEALTH,
            source_id=instance.id,
            description=f"Evento de sanidad pendiente de ({instance.farm.name} en ({instance.cycle.name}))",
            message=f"Evento de sanidad programado en ({instance.farm.name}) para ({instance.cycle.name})\nFecha {instance.date} no cumplido.",
            severity=Alert.Severity.MEDIUM,
        )
    else:
        resolve_alert(source_type=Alert.SourceType.HEALTH, source_id=instance.id)
