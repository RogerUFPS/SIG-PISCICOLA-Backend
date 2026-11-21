# purchases/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import Alert
from apps.core.utils import create_alert

from .models import InventoryMovement
from .utils import get_product_stock


@receiver(post_save, sender=InventoryMovement)
def check_stock_threshold(sender, instance, created, **kwargs):
    if not created:
        return

    product = instance.product
    if product.minimun_stock_threshold <= 0:
        return

    stock_actual = get_product_stock(product.id, instance.farm_id)

    if stock_actual <= product.minimun_stock_threshold:
        create_alert(
            farm=instance.farm,
            source_type=Alert.SourceType.STOCK,
            source_id=product.id,
            description=f"Stock bajo para '{product.name}'",
            message=(
                f"El stock actual de '{product.name}' es {stock_actual} {product.unit.symbol}, "
                f"por debajo del umbral mínimo de {product.minimun_stock_threshold}."
            ),
            value=stock_actual,
            threshold=product.minimun_stock_threshold,
            severity=(
                Alert.Severity.HIGH if stock_actual == 0 else Alert.Severity.MEDIUM
            ),
        )
