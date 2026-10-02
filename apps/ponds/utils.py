# utils.py

import uuid

from django.utils import timezone

from .models import Pond, UserFarmPond


def generate_pond_code() -> str:
    return f"PND-{uuid.uuid4().hex[:8].upper()}"


def get_pond_or_404(farm, pond_id) -> Pond:
    try:
        return Pond.objects.get(pk=pond_id, farm=farm, deleted_at__isnull=True)
    except Pond.DoesNotExist:
        return None


def soft_delete_pond(pond: Pond) -> None:
    from apps.batch.models import PondBatch
    from apps.cycle.models import Cycle

    has_active_cycle = Cycle.objects.filter(
        pond=pond,
        deleted_at__isnull=True,
        state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
    ).exists()
    has_active_planting = PondBatch.objects.filter(
        pond=pond,
        end_date__isnull=True,
        current_quantity__gt=0,
    ).exists()

    if has_active_cycle or has_active_planting:
        raise ValueError(
            "No se puede eliminar el estanque porque tiene un ciclo o siembra activa."
        )

    pond.deleted_at = timezone.now()
    pond.save(update_fields=["deleted_at"])


def pond_has_cycles(pond: Pond) -> bool:
    from apps.cycle.models import Cycle

    return Cycle.objects.filter(pond=pond, deleted_at__isnull=True).exists()


def get_pond_members(pond: Pond):
    return UserFarmPond.objects.filter(pond=pond).select_related("user")


def remove_pond_member(farm, pond: Pond, user_id: int) -> bool:
    deleted, _ = UserFarmPond.objects.filter(
        pond=pond,
        farm=farm,
        user_id=user_id,
    ).delete()
    return deleted > 0
