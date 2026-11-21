# utils.py
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import Buy, InventoryMovement, PurchaseDetail


def _create_inventory_movement(buy: Buy, detail: PurchaseDetail) -> InventoryMovement:
    return InventoryMovement.objects.create(
        farm=buy.farm,
        product=detail.product,
        movement_type=InventoryMovement.MovementType.IN,
        quantity=detail.quantity,
        unit_cost=detail.unit_value,
        total_cost=detail.total_value,
        observations=buy.comments,
        source_type=InventoryMovement.SourceType.PURCHASE,
        source_id=detail.id,
    )


def create_out_movement(
    *,
    farm,
    product,
    quantity,
    source_type: str,
    source_id: int,
    observations: str = "",
    pond=None,
    cycle=None,
    unit_cost: float = 0,
) -> InventoryMovement:
    stock_actual = get_product_stock(product.id, farm.id)
    if float(quantity) > stock_actual:
        raise ValueError(
            f"Stock insuficiente para '{product.name}'. "
            f"Disponible: {stock_actual}, solicitado: {quantity}."
        )

    return InventoryMovement.objects.create(
        farm=farm,
        product=product,
        movement_type=InventoryMovement.MovementType.OUT,
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=unit_cost * float(quantity),
        observations=observations,
        source_type=source_type,
        source_id=source_id,
        pond_id=pond,
        cycle_id=cycle,
    )


def _delete_details_with_movements(buy: Buy) -> None:
    detail_ids = buy.details.values_list("id", flat=True)
    InventoryMovement.objects.filter(
        source_type=InventoryMovement.SourceType.PURCHASE,
        source_id__in=detail_ids,
    ).delete()
    buy.details.all().delete()


def get_product_stock(product_id: int, farm_id: int) -> float:

    from .models import InventoryMovement as IM

    result = InventoryMovement.objects.filter(
        product_id=product_id,
        farm_id=farm_id,
    ).aggregate(
        total_in=Sum(
            "quantity",
            filter=Q(movement_type__in=[IM.MovementType.IN, IM.MovementType.INITIAL]),
        ),
        total_out=Sum("quantity", filter=Q(movement_type=IM.MovementType.OUT)),
    )
    return float((result["total_in"] or 0) - (result["total_out"] or 0))


@transaction.atomic
def _maybe_create_batch_from_purchase(detail: PurchaseDetail, batch_data: dict) -> None:
    from apps.batch.models import Batch

    if detail.product.type_product.name.lower() != "lote":
        return

    farm = detail.buy.farm
    timestamp = int(timezone.now().timestamp())
    code = f"BATCH-{farm.id}-{timestamp}"
    while Batch.objects.filter(code=code, farm=farm).exists():
        timestamp += 1
        code = f"BATCH-{farm.id}-{timestamp}"

    Batch.objects.create(
        farm=farm,
        code=code,
        origin_type=Batch.OriginType.PURCHASE_DETAIL,
        origin_id=detail.id,
        specie_id=batch_data["specie_id"],
        biological_state=batch_data.get(
            "biological_state", Batch.BiologicalState.ALEVIN
        ),
        status=Batch.Status.ACTIVE,
        initial_quantity=int(detail.quantity),
        min_weight_g=batch_data["min_weight_g"],
        avg_weight_g=batch_data["avg_weight_g"],
        max_weight_g=batch_data["max_weight_g"],
        comments=batch_data.get("comments", ""),
    )
