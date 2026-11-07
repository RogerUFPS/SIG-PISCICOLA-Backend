from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Q, QuerySet, Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.signals import audit_bulk_create, audit_queryset_update
from apps.harvest.models import (HarvestClassification,
                                 HarvestClassificationDerivation)

from .models import Client, Sale, SaleDetail

User = get_user_model()
logger = logging.getLogger(__name__)

EDIT_WINDOW_MINUTES: int = 15


def _is_within_edit_window(reference_dt) -> bool:
    return timezone.now() <= reference_dt + timedelta(minutes=EDIT_WINDOW_MINUTES)


def _get_sale_or_404(sale_id: int) -> Sale:
    try:
        return (
            Sale.objects.select_related("client", "farm", "created_by")
            .prefetch_related("details__harvest_classification")
            .get(pk=sale_id)
        )
    except Sale.DoesNotExist:
        raise ValidationError({"detail": f"Venta con id={sale_id} no encontrada."})


def _get_detail_or_404(detail_id: int) -> SaleDetail:
    try:
        return SaleDetail.objects.select_related("sale", "harvest_classification").get(
            pk=detail_id
        )
    except SaleDetail.DoesNotExist:
        raise ValidationError(
            {"detail": f"Detalle de venta con id={detail_id} no encontrado."}
        )


def _notify_sale_created(sale: Sale) -> None:
    deadline = sale.created_at + timedelta(minutes=EDIT_WINDOW_MINUTES)
    logger.info(
        "[Sale #%s] Creada por user_id=%s. Ventana de edición cierra a las %s.",
        sale.invoice_number,
        sale.created_by_id,
        deadline.strftime("%H:%M"),
    )


def _recalculate_sale_total(sale: Sale) -> Decimal:
    total = SaleDetail.objects.filter(sale=sale).aggregate(total=Sum("price"))[
        "total"
    ] or Decimal("0")
    audit_queryset_update(
        Sale.objects.filter(pk=sale.pk),
        total=total,
    )
    sale.total = total
    return total


def get_classification_available_weight_g(
    classification: HarvestClassification,
    exclude_detail_id: int | None = None,
) -> Decimal:
    derived_weight = HarvestClassificationDerivation.objects.filter(
        classification=classification
    ).aggregate(total=Sum("total_weight_g"))["total"] or Decimal("0")

    sold_qs = SaleDetail.objects.filter(harvest_classification=classification)
    if exclude_detail_id is not None:
        sold_qs = sold_qs.exclude(pk=exclude_detail_id)
    sold_weight = sold_qs.aggregate(total=Sum("quantity_g"))["total"] or Decimal("0")

    total_weight = Decimal(str(classification.total_weight_g))
    available = total_weight - derived_weight - sold_weight
    return max(available, Decimal("0"))


def get_classification_available_fish_count_for_sale(
    classification: HarvestClassification,
    exclude_detail_id: int | None = None,
) -> int:
    total = classification.fish_count
    if not total:
        return 0

    derived = (
        HarvestClassificationDerivation.objects.filter(
            classification=classification
        ).aggregate(used=Sum("fish_count"))["used"]
        or 0
    )

    sold_qs = SaleDetail.objects.filter(
        harvest_classification=classification,
        fish_count__isnull=False,
    )
    if exclude_detail_id is not None:
        sold_qs = sold_qs.exclude(pk=exclude_detail_id)
    sold = sold_qs.aggregate(used=Sum("fish_count"))["used"] or 0

    return max(0, total - derived - sold)


def _validate_weight(
    classification: HarvestClassification,
    requested_quantity: Decimal,
    exclude_detail_id: int | None = None,
) -> None:
    available = get_classification_available_weight_g(classification, exclude_detail_id)
    if requested_quantity > available:
        raise ValidationError(
            {
                "quantity_g": (
                    f"Peso solicitado ({requested_quantity} g) supera el disponible "
                    f"({available} g) para la clasificación '{classification}'."
                )
            }
        )


def _validate_fish_count(
    classification: HarvestClassification,
    requested_fish: int,
    exclude_detail_id: int | None = None,
) -> None:
    available = get_classification_available_fish_count_for_sale(
        classification, exclude_detail_id
    )
    if requested_fish > available:
        raise ValidationError(
            {
                "fish_count": (
                    f"Cantidad de peces solicitada ({requested_fish}) supera la disponible "
                    f"({available}) para la clasificación '{classification}'."
                )
            }
        )


def create_client(data: dict[str, Any]) -> Client:
    return Client.objects.create(**data)


def list_clients(filters: dict[str, Any] | None = None) -> QuerySet[Client]:
    filters = filters or {}
    qs = Client.objects.select_related("farm").all()
    if farm_id := filters.get("farm_id"):
        qs = qs.filter(farm_id=farm_id)
    if client_type := filters.get("client_type"):
        qs = qs.filter(client_type=client_type)
    if document_type := filters.get("document_type"):
        qs = qs.filter(document_type=document_type)
    if search := filters.get("search"):
        qs = qs.filter(Q(name__icontains=search) | Q(document_number__icontains=search))
    return qs.order_by("name")


def get_client(client_id: int, *, farm_id: int | None = None) -> Client:
    try:
        client = Client.objects.select_related("farm").get(pk=client_id)
    except Client.DoesNotExist:
        raise ValidationError({"detail": f"Cliente con id={client_id} no encontrado."})
    if farm_id is not None and client.farm_id != farm_id:
        raise ValidationError({"detail": f"Cliente con id={client_id} no encontrado."})
    return client


def update_client(client_id: int, data: dict[str, Any]) -> Client:
    client = get_client(client_id)
    for field, value in data.items():
        setattr(client, field, value)
    client.save()
    return client


def can_delete_client(client_id: int) -> bool:
    return not Sale.objects.filter(client_id=client_id).exists()


def delete_client(client_id: int) -> None:
    if not can_delete_client(client_id):
        raise ValidationError(
            {
                "detail": (
                    "No es posible eliminar el cliente porque tiene ventas asociadas. "
                    "Considere desactivarlo en su lugar."
                )
            }
        )
    client = get_client(client_id)
    client.delete()


def list_sales(filters: dict[str, Any] | None = None) -> QuerySet[Sale]:
    filters = filters or {}
    qs = Sale.objects.select_related("farm", "client", "created_by")
    if farm_id := filters.get("farm_id"):
        qs = qs.filter(farm_id=farm_id)
    if client_id := filters.get("client_id"):
        qs = qs.filter(client_id=client_id)
    if payment_method := filters.get("payment_method"):
        qs = qs.filter(payment_method=payment_method)
    if date_from := filters.get("date_from"):
        qs = qs.filter(date__gte=date_from)
    if date_to := filters.get("date_to"):
        qs = qs.filter(date__lte=date_to)
    if invoice_number := filters.get("invoice_number"):
        qs = qs.filter(invoice_number__icontains=invoice_number)
    return qs.order_by("-created_at")


def list_sales_client(client_id: int, *, farm_id: int | None = None) -> QuerySet[Sale]:
    qs = (
        Sale.objects.select_related("farm", "client", "created_by")
        .filter(client_id=client_id)
        .order_by("-created_at")
    )
    if farm_id is not None:
        qs = qs.filter(farm_id=farm_id)
    return qs


def list_sales_harvest_classification(
    harvest_classification_id: int,
    *,
    farm_id: int | None = None,
) -> QuerySet[Sale]:
    qs = (
        Sale.objects.select_related("farm", "client", "created_by")
        .prefetch_related("details__harvest_classification")
        .filter(details__harvest_classification_id=harvest_classification_id)
        .distinct()
        .order_by("-created_at")
    )
    if farm_id is not None:
        qs = qs.filter(farm_id=farm_id)
    return qs


def get_sale(sale_id: int, *, farm_id: int | None = None) -> Sale:
    sale = _get_sale_or_404(sale_id)
    if farm_id is not None and sale.farm_id != farm_id:
        raise ValidationError({"detail": f"Venta con id={sale_id} no encontrada."})
    return sale


def can_edit_sale(sale_id: int) -> bool:
    sale = _get_sale_or_404(sale_id)
    return _is_within_edit_window(sale.created_at)


def edit_sale(sale_id: int, data: dict[str, Any]) -> Sale:
    sale = _get_sale_or_404(sale_id)
    within_window = _is_within_edit_window(sale.created_at)

    FULL_EDITABLE_FIELDS = frozenset(
        {"client", "invoice_number", "payment_method", "observations", "date"}
    )
    OBSERVATIONS_ONLY = frozenset({"observations"})

    allowed = FULL_EDITABLE_FIELDS if within_window else OBSERVATIONS_ONLY
    restricted = set(data.keys()) - allowed
    if restricted:
        raise PermissionDenied(
            f"Han transcurrido más de {EDIT_WINDOW_MINUTES} minutos desde la creación de la venta. "
            f"Solo se puede modificar 'observations'. "
            f"Campos no permitidos: {', '.join(sorted(restricted))}."
        )

    for field, value in data.items():
        setattr(sale, field, value)
    sale.save()
    return sale


def update_sale_observations(sale_id: int, observations: str) -> Sale:
    sale = _get_sale_or_404(sale_id)
    sale.observations = observations
    sale.save(update_fields=["observations", "updated_at"])
    return sale


def list_sale_details_by_sale(sale_id: int) -> QuerySet[SaleDetail]:
    return (
        SaleDetail.objects.select_related("harvest_classification")
        .filter(sale_id=sale_id)
        .order_by("pk")
    )


def can_edit_sale_detail(detail_id: int) -> bool:
    detail = _get_detail_or_404(detail_id)
    return _is_within_edit_window(detail.sale.created_at)


@transaction.atomic
def edit_sale_detail(detail_id: int, data: dict[str, Any]) -> SaleDetail:
    detail = _get_detail_or_404(detail_id)

    if not _is_within_edit_window(detail.sale.created_at):
        raise PermissionDenied(
            f"Han transcurrido más de {EDIT_WINDOW_MINUTES} minutos desde la creación de la venta. "
            "Los detalles ya no pueden ser modificados."
        )

    changing_quantity = "quantity_g" in data
    changing_classification = (
        "harvest_classification" in data
        and data["harvest_classification"].pk != detail.harvest_classification_id
    )

    if changing_quantity or changing_classification:
        new_quantity = data.get("quantity_g", detail.quantity_g)
        target_classification = data.get(
            "harvest_classification", detail.harvest_classification
        )
        target_classification = HarvestClassification.objects.select_for_update().get(
            pk=target_classification.pk
        )
        exclude_id = detail.pk if not changing_classification else None
        _validate_weight(
            target_classification, new_quantity, exclude_detail_id=exclude_id
        )

    for field, value in data.items():
        setattr(detail, field, value)
    detail.save()

    _recalculate_sale_total(detail.sale)
    return detail


@transaction.atomic
def create_full_sale(
    sale_data: dict[str, Any],
    details_data: list[dict[str, Any]],
    created_by: User,
) -> Sale:
    if not details_data:
        raise ValidationError(
            {"details": "Una venta debe contener al menos un detalle."}
        )

    seen_classification_ids: set[int] = set()
    for item in details_data:
        cid = item["harvest_classification"].pk
        if cid in seen_classification_ids:
            raise ValidationError(
                {
                    "details": (
                        f"La clasificación id={cid} aparece más de una vez. "
                        "Cada clasificación debe tener un único detalle por venta."
                    )
                }
            )
        seen_classification_ids.add(cid)

    locked_classifications = {
        c.pk: c
        for c in HarvestClassification.objects.select_for_update().filter(
            pk__in=seen_classification_ids
        )
    }

    if missing := seen_classification_ids - locked_classifications.keys():
        raise ValidationError(
            {"details": f"Clasificaciones no encontradas: {missing}."}
        )

    consumed_weight_tx: dict[int, Decimal] = {}
    consumed_fish_tx: dict[int, int] = {}
    running_total = Decimal("0")

    for item in details_data:
        classification = locked_classifications[item["harvest_classification"].pk]
        quantity = item["quantity_g"]
        fish_count = item.get("fish_count")
        price = item["price"]

        already_consumed_weight = consumed_weight_tx.get(
            classification.pk, Decimal("0")
        )
        db_available_weight = get_classification_available_weight_g(classification)
        effective_available_weight = db_available_weight - already_consumed_weight
        if quantity > effective_available_weight:
            raise ValidationError(
                {
                    "quantity_g": (
                        f"Peso solicitado ({quantity} g) supera el disponible "
                        f"({effective_available_weight} g) para '{classification}'."
                    )
                }
            )

        if fish_count is not None:
            already_consumed_fish = consumed_fish_tx.get(classification.pk, 0)
            db_available_fish = get_classification_available_fish_count_for_sale(
                classification
            )
            effective_available_fish = db_available_fish - already_consumed_fish
            if fish_count > effective_available_fish:
                raise ValidationError(
                    {
                        "fish_count": (
                            f"Peces solicitados ({fish_count}) superan los disponibles "
                            f"({effective_available_fish}) para '{classification}'."
                        )
                    }
                )

        consumed_weight_tx[classification.pk] = already_consumed_weight + quantity
        if fish_count is not None:
            consumed_fish_tx[classification.pk] = already_consumed_fish + fish_count

        running_total += price

    sale = Sale.objects.create(**sale_data, created_by=created_by, total=running_total)

    audit_bulk_create(
        SaleDetail,
        [
            SaleDetail(
                farm=item["farm"],
                sale=sale,
                harvest_classification=locked_classifications[
                    item["harvest_classification"].pk
                ],
                quantity_g=item["quantity_g"],
                fish_count=item.get("fish_count"),
                price=item["price"],
            )
            for item in details_data
        ]
    )

    _notify_sale_created(sale)
    return sale
