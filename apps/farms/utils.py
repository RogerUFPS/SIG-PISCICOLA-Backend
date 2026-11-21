from .models import FarmRole, FarmRoleAppPermission, UserFarm


def get_all_farm_permissions() -> list[dict[str, str]]:
    from .modules import MODULES, OPERATIONS

    return [
        {"module": module, "operation": operation}
        for module in sorted(MODULES)
        for operation in OPERATIONS
        if module not in ("alerts", "audit_logs") or operation == "view"
    ]


def get_effective_permissions(user_farm: UserFarm) -> list[dict[str, str]]:
    if user_farm.is_owner:
        return get_all_farm_permissions()

    grants = set(
        user_farm.personal_permissions.values_list("module", "operation")
    )
    role = user_farm.farm_role
    if (
        role is not None
        and role.deleted_at is None
        and role.farm_id == user_farm.farm_id
    ):
        for permission in FarmRoleAppPermission.objects.filter(role=role):
            for operation, enabled in (
                ("view", permission.can_view),
                ("create", permission.can_create),
                ("update", permission.can_update),
                ("delete", permission.can_delete),
            ):
                if enabled:
                    grants.add((permission.module, operation))
    return [
        {"module": module, "operation": operation}
        for module, operation in sorted(grants)
    ]


def assign_role_to_operario(user_farm: UserFarm, role: FarmRole) -> None:
    if role.farm_id != user_farm.farm_id:
        raise ValueError("El rol no pertenece a esta finca.")

    user_farm.farm_role = role
    user_farm.save(update_fields=["farm_role"])


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
