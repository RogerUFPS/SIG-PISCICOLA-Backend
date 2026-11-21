from apps.batch.models import Batch, BatchSource, BatchTransfer, PondBatch
from apps.cycle.models import CyclePondBatch
from apps.harvest.models import HarvestSource
from apps.monitoring.models import FishEvaluated
from apps.purchases.models import PurchaseDetail


def _batch_family(batch: Batch) -> tuple[set[int], list[BatchSource]]:
    family_ids = {batch.pk}
    links: list[BatchSource] = []
    pending = [batch.pk]

    while pending:
        current = pending.pop()
        current_links = list(
            BatchSource.objects.filter(parent_batch_id=current).select_related(
                "parent_batch", "child_batch"
            )
        ) + list(
            BatchSource.objects.filter(child_batch_id=current).select_related(
                "parent_batch", "child_batch"
            )
        )
        for link in current_links:
            if all(existing.pk != link.pk for existing in links):
                links.append(link)
            for related_id in (link.parent_batch_id, link.child_batch_id):
                if related_id not in family_ids:
                    family_ids.add(related_id)
                    pending.append(related_id)
    return family_ids, links


def collect_batch_traceability(batch: Batch) -> dict:
    family_ids, links = _batch_family(batch)
    family = Batch.objects.filter(pk__in=family_ids).select_related("specie")

    origins = []
    for related_batch in family:
        if (
            related_batch.origin_type == Batch.OriginType.PURCHASE_DETAIL
            and related_batch.origin_id
        ):
            detail = (
                PurchaseDetail.objects.filter(pk=related_batch.origin_id)
                .select_related("buy__supplier", "product", "unit")
                .first()
            )
            if detail:
                supplier = detail.buy.supplier
                origins.append(
                    {
                        "batch_id": related_batch.id,
                        "batch_code": related_batch.code,
                        "type": "purchase",
                        "purchase_id": detail.buy_id,
                        "purchase_detail_id": detail.id,
                        "date": str(detail.buy.date),
                        "invoice_number": detail.buy.invoice_number,
                        "supplier": supplier.name if supplier else None,
                        "supplier_document": (
                            f"{supplier.document_type} {supplier.document_number}"
                            if supplier
                            else None
                        ),
                        "product": detail.product.name,
                        "quantity": str(detail.quantity),
                        "unit": detail.unit.symbol,
                    }
                )
        elif related_batch.origin_type == Batch.OriginType.INITIAL:
            origins.append(
                {
                    "batch_id": related_batch.id,
                    "batch_code": related_batch.code,
                    "type": "initial",
                    "date": related_batch.created_at.date().isoformat(),
                }
            )

    pond_assignments = [
        {
            "id": pb.id,
            "batch_id": pb.batch_id,
            "batch_code": pb.batch.code,
            "pond_id": pb.pond_id,
            "pond": pb.pond.name,
            "initial_quantity": pb.initial_quantity,
            "current_quantity": pb.current_quantity,
            "start_date": str(pb.start_date),
            "end_date": str(pb.end_date) if pb.end_date else None,
        }
        for pb in PondBatch.objects.filter(batch_id__in=family_ids).select_related(
            "batch", "pond"
        )
    ]

    cycle_links = list(
        CyclePondBatch.objects.filter(pond_batch__batch_id__in=family_ids)
        .select_related("cycle", "cycle__pond", "pond_batch__batch")
        .order_by("cycle__start_date", "id")
    )
    cycles = [
        {
            "cycle_id": cpb.cycle_id,
            "cycle": cpb.cycle.name,
            "state": cpb.cycle.state,
            "pond": cpb.cycle.pond.name,
            "batch_id": cpb.pond_batch.batch_id,
            "batch_code": cpb.pond_batch.batch.code,
            "quantity": cpb.quantity,
            "start_date": str(cpb.cycle.start_date),
            "estimated_finish_date": str(cpb.cycle.estimated_finish_date),
            "finish_date": str(cpb.cycle.finish_date) if cpb.cycle.finish_date else None,
        }
        for cpb in cycle_links
    ]

    cycle_ids = {cpb.cycle_id for cpb in cycle_links}
    growth = [
        {
            "cycle_id": evaluation.cycle_id,
            "cycle": evaluation.cycle.name,
            "pond": evaluation.pond.name,
            "date": str(evaluation.evaluation_date),
            "sampled_quantity": evaluation.sampled_quantity,
            "min_weight_g": evaluation.min_weight_g,
            "avg_weight_g": evaluation.avg_weight_g,
            "max_weight_g": evaluation.max_weight_g,
            "mortality_quantity": evaluation.mortality_quantity,
        }
        for evaluation in FishEvaluated.objects.filter(
            cycle_id__in=cycle_ids,
            deleted_at__isnull=True,
        )
        .select_related("cycle", "pond")
        .order_by("evaluation_date", "id")
    ]

    transfers = [
        {
            "id": transfer.id,
            "source_batch": transfer.source_pond_batch.batch.code,
            "destination_batch": transfer.to_pond_batch.batch.code,
            "from_pond": transfer.source_pond_batch.pond.name,
            "to_pond": transfer.to_pond_batch.pond.name,
            "quantity": transfer.quantity,
            "date": str(transfer.date),
            "reason": transfer.reason,
        }
        for transfer in BatchTransfer.objects.filter(
            source_pond_batch__batch_id__in=family_ids
        )
        .select_related(
            "source_pond_batch__batch",
            "source_pond_batch__pond",
            "to_pond_batch__batch",
            "to_pond_batch__pond",
        )
        .order_by("date", "id")
    ]

    cpb_ids = [cpb.id for cpb in cycle_links]
    harvests = [
        {
            "harvest_id": source.harvest_id,
            "cycle": source.harvest.cycle.name,
            "date": str(source.harvest.date),
            "type": source.harvest.type,
            "fish_count": source.fish_count,
            "total_weight_g": str(source.total_weight_g),
            "traceability_type": source.traceability_type,
        }
        for source in HarvestSource.objects.filter(
            cycle_pond_batch_id__in=cpb_ids
        )
        .select_related("harvest", "harvest__cycle")
        .order_by("harvest__date", "id")
    ]

    return {
        "batch": {
            "id": batch.id,
            "code": batch.code,
            "specie": str(batch.specie),
            "biological_state": batch.biological_state,
            "status": batch.status,
            "initial_quantity": batch.initial_quantity,
            "created_at": batch.created_at.isoformat(),
        },
        "origins": origins,
        "genealogy": [
            {
                "parent_id": link.parent_batch_id,
                "parent_code": link.parent_batch.code,
                "child_id": link.child_batch_id,
                "child_code": link.child_batch.code,
                "quantity": link.quantity,
            }
            for link in links
        ],
        "pond_assignments": pond_assignments,
        "cycles": cycles,
        "growth": growth,
        "transfers": transfers,
        "harvests": harvests,
    }
