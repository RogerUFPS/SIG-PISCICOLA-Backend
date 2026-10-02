from apps.accounts.permissions import ROLE_ADMIN, ROLE_PRODUCTOR

from .enums import FarmPermission, expand_permissions
from .models import FarmRole, UserFarm
from .permissions import _get_user_farm


def user_has_farm_permission(user, farm_id: int, permission: FarmPermission) -> bool:
    role = getattr(user, "role", None)
    if role is None or not user.is_authenticated:
        return False
    if role.name == ROLE_ADMIN:
        return True
    uf = _get_user_farm(user, farm_id)
    if uf is None:
        return False
    if uf.is_owner:
        return True
    if role.name == ROLE_PRODUCTOR:
        return True
    return bool(expand_permissions(uf.permissions) & permission)


def get_effective_permissions(user_farm: UserFarm) -> int:
    if user_farm.is_owner:
        return int(FarmPermission.ALL)
    return expand_permissions(user_farm.permissions)


def assign_operario_permissions(user_farm: UserFarm, permissions: list[str]) -> None:
    result = 0
    for name in permissions:
        try:
            perm = FarmPermission[name]
        except KeyError:
            raise ValueError(f"Permiso inválido: '{name}'.")
        result |= perm
    user_farm.permissions = int(result)
    user_farm.save(update_fields=["permissions"])


def assign_role_to_operario(user_farm: UserFarm, role: FarmRole) -> None:
    if role.farm_id != user_farm.farm_id:
        raise ValueError("El rol no pertenece a esta finca.")

    user_farm.farm_role = role
    user_farm.permissions = int(role.permissions)
    user_farm.save(update_fields=["farm_role", "permissions"])


def farm_has_active_resources(farm) -> bool:
    from apps.cycle.models import Cycle
    from apps.ponds.models import Pond

    return (
        Cycle.objects.filter(
            farm=farm,
            deleted_at__isnull=True,
            state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
        ).exists()
        or Pond.objects.filter(
            farm=farm,
            deleted_at__isnull=True,
        )
        .exclude(status=Pond.Status.INACTIVE)
        .exists()
    )
