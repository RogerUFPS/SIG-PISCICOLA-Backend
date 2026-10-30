# enums.py
from enum import IntFlag


class FarmPermission(IntFlag):
    MANAGE_REVIEWS = 1 << 0  #  1
    MANAGE_INVENTORY = 1 << 1  #  2
    MANAGE_CYCLE = 1 << 2  #  4
    MANAGE_POND = 1 << 3  #  8
    MANAGE_FARM = 1 << 4  # 16
    MANAGE_USERS = 1 << 5  # 32

    ALL = (1 << 6) - 1  # 63

    @classmethod
    def choices(cls):
        return [(p.name, p.name) for p in cls if p != cls.ALL]


PERMISSION_IMPLIES: dict[FarmPermission, FarmPermission] = {
    FarmPermission.MANAGE_FARM: FarmPermission.ALL,
    FarmPermission.MANAGE_POND: (
        FarmPermission.MANAGE_POND
        | FarmPermission.MANAGE_CYCLE
        | FarmPermission.MANAGE_REVIEWS
    ),
    FarmPermission.MANAGE_CYCLE: (
        FarmPermission.MANAGE_CYCLE | FarmPermission.MANAGE_REVIEWS
    ),
    FarmPermission.MANAGE_INVENTORY: FarmPermission.MANAGE_INVENTORY,
    FarmPermission.MANAGE_REVIEWS: FarmPermission.MANAGE_REVIEWS,
    FarmPermission.MANAGE_USERS: FarmPermission.MANAGE_USERS,
}


def expand_permissions(stored: int) -> int:
    result = 0
    for perm, implied in PERMISSION_IMPLIES.items():
        if stored & perm:
            result |= int(implied)
    return result


def effective_farm_permissions(membership) -> int:
    if membership.is_owner:
        return int(FarmPermission.ALL)

    stored = membership.permissions
    farm_role = getattr(membership, "farm_role", None)
    if (
        farm_role is not None
        and farm_role.deleted_at is None
        and farm_role.farm_id == membership.farm_id
    ):
        stored |= farm_role.permissions
    return expand_permissions(stored)
