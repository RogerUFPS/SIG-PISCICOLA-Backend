from datetime import date

from apps.batch.models import PondBatch
from django.db import transaction
from django.utils import timezone


def _resolve_pond_batches_for_update(*pond_batches):
    ids = sorted(
        {pb.pk if isinstance(pb, PondBatch) else int(pb) for pb in pond_batches}
    )
    locked = {
        pb.id: pb for pb in PondBatch.objects.filter(id__in=ids).select_for_update()
    }
    result = []
    for pb in pond_batches:
        key = pb.pk if isinstance(pb, PondBatch) else int(pb)
        result.append(locked[key])
    return result


@transaction.atomic
def adjust_pond_batch_quantity(pond_batch, delta: int) -> PondBatch:
    pond_batch = _resolve_pond_batches_for_update(pond_batch)[0]

    if delta == 0:
        return pond_batch

    if delta < 0 and abs(delta) > pond_batch.current_quantity:
        raise ValueError(
            f"La cantidad solicitada ({abs(delta)}) excede el stock disponible "
            f"({pond_batch.current_quantity})."
        )

    pond_batch.current_quantity += delta
    if pond_batch.current_quantity < 0:
        raise ValueError(
            f"No se puede dejar current_quantity en negativo ({pond_batch.current_quantity})."
        )

    update_fields = ["current_quantity"]
    if pond_batch.current_quantity == 0 and pond_batch.end_date is None:
        pond_batch.end_date = timezone.now().date()
        update_fields.append("end_date")
    elif pond_batch.current_quantity > 0 and pond_batch.end_date is not None:
        pond_batch.end_date = None
        update_fields.append("end_date")

    pond_batch.save(update_fields=update_fields)
    return pond_batch


@transaction.atomic
def transfer_pond_batch_quantity(
    source_pond_batch, destination_pond_batch, quantity: int
):
    if quantity <= 0:
        raise ValueError("La cantidad debe ser mayor a 0.")

    source, destination = _resolve_pond_batches_for_update(
        source_pond_batch,
        destination_pond_batch,
    )

    if source.pk == destination.pk:
        raise ValueError("El origen y destino no pueden ser el mismo PondBatch.")

    if quantity > source.current_quantity:
        raise ValueError(
            f"La cantidad solicitada ({quantity}) excede el stock disponible "
            f"({source.current_quantity})."
        )

    source.current_quantity -= quantity
    destination.current_quantity += quantity

    source_update_fields = ["current_quantity"]
    if source.current_quantity == 0 and source.end_date is None:
        source.end_date = timezone.now().date()
        source_update_fields.append("end_date")

    destination_update_fields = ["current_quantity"]
    if destination.current_quantity > 0 and destination.end_date is not None:
        destination.end_date = None
        destination_update_fields.append("end_date")

    source.save(update_fields=source_update_fields)
    destination.save(update_fields=destination_update_fields)
    return source, destination


def _fk_pk(value):
    """Normaliza FK para PondBatchSerializer.data (espera PK, no instancias de modelo)."""
    return value.pk if hasattr(value, "pk") else value


@transaction.atomic
def create_pond_batch(
    *, pond, batch, initial_quantity: int, start_date: date | None = None
) -> PondBatch:
    from apps.batch.serializers import PondBatchSerializer

    if start_date is None:
        start_date = timezone.now().date()

    serializer = PondBatchSerializer(
        data={
            "pond": _fk_pk(pond),
            "batch": _fk_pk(batch),
            "initial_quantity": initial_quantity,
            "start_date": start_date,
        }
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save()
