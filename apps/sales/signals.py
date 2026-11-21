from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import Alert
from apps.core.utils import create_alert

from .models import Sale


@receiver(post_save, sender=Sale)
def sale_created_alert(sender, instance, created, **kwargs):
    if not created:
        return

    user_name = instance.created_by.get_full_name() or instance.created_by.username

    message = (
        f"Venta #{instance.invoice_number} registrada por {user_name}. "
        f"Monto total: ${instance.total:,.2f}. "
        f"Fecha: {instance.date}. "
        f"Tienes 15 minutos para editarla."
    )

    create_alert(
        farm=instance.farm,
        source_type=Alert.SourceType.SALE,
        source_id=instance.id,
        description=f"Venta {instance.invoice_number} creada, tienes 15 minutos para editarla en caso de errores",
        message=message,
        severity=Alert.Severity.LOW,
    )
