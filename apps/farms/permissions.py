from rest_framework.permissions import BasePermission

from apps.accounts.permissions import ROLE_ADMIN

from .enums import FarmPermission, expand_permissions
from .models import UserFarm


def _get_farm_pk(view, request=None):
    farm_pk = (
        view.kwargs.get("farm_pk")
        or view.kwargs.get("farm_id")
        or view.kwargs.get("pk")
    )
    if farm_pk is not None or request is None:
        return farm_pk
    request_data = getattr(request, "data", {})
    query_params = getattr(request, "query_params", getattr(request, "GET", {}))
    return (
        request_data.get("farm_id")
        or query_params.get("farm_id")
    )


def _get_user_farm(user, farm_pk) -> UserFarm | None:
    if not user.is_authenticated:
        return None
    try:
        uf = UserFarm.objects.select_related("farm").get(
            user=user,
            farm_id=farm_pk,
            farm__deleted_at__isnull=True,
        )
    except UserFarm.DoesNotExist:
        return None
    if uf.status != UserFarm.Status.ACTIVE and not uf.is_owner:
        return None
    return uf


def user_may_access_farm(user, farm_pk) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    role = getattr(user, "role", None)
    if role is None:
        return False
    if role.name == ROLE_ADMIN:
        return True
    return _get_user_farm(user, farm_pk) is not None


class IsFarmMember(BasePermission):

    def has_permission(self, request, view):
        farm_pk = _get_farm_pk(view, request)
        if farm_pk is None:
            if not request.user.is_authenticated:
                return False
            if getattr(getattr(request.user, "role", None), "name", None) == ROLE_ADMIN:
                return True
            return UserFarm.objects.filter(
                user=request.user,
                status=UserFarm.Status.ACTIVE,
                farm__deleted_at__isnull=True,
            ).exists()
        if not user_may_access_farm(request.user, farm_pk):
            return False
        from apps.accounts.permissions import AppPermission

        return AppPermission().has_permission(request, view)


class IsFarmOwner(BasePermission):
    def has_permission(self, request, view):
        farm_pk = _get_farm_pk(view, request)
        if farm_pk is None:
            return False
        if not request.user.is_authenticated:
            return False
        role = getattr(request.user, "role", None)
        if role is None:
            return False
        if role.name == ROLE_ADMIN:
            return True
        uf = _get_user_farm(request.user, farm_pk)
        return bool(uf and uf.is_owner)


class HasFarmPermission(BasePermission):
    required_permission: FarmPermission = FarmPermission.MANAGE_REVIEWS

    def has_permission(self, request, view):
        farm_pk = _get_farm_pk(view, request)
        if farm_pk is None:
            return False
        if not request.user.is_authenticated:
            return False
        role = getattr(request.user, "role", None)
        if role is None:
            return False
        if role.name == ROLE_ADMIN:
            return True

        uf = _get_user_farm(request.user, farm_pk)
        if uf is None:
            return False
        if uf.is_owner:
            return True
        if uf.farm_role and (
            uf.farm_role.farm_id != uf.farm_id
            or uf.farm_role.deleted_at is not None
        ):
            return False
        from apps.accounts.permissions import AppPermission

        if AppPermission().has_permission(request, view):
            return True

        effective = expand_permissions(uf.permissions)
        return bool(effective & self.required_permission)


class CanManageFarmUsers(BasePermission):
    def has_permission(self, request, view):
        farm_pk = _get_farm_pk(view, request)
        if farm_pk is None:
            return False
        if not request.user.is_authenticated:
            return False
        role = getattr(request.user, "role", None)
        if role is None:
            return False
        if role.name == ROLE_ADMIN:
            return True

        uf = _get_user_farm(request.user, farm_pk)
        if uf is None:
            return False
        if uf.is_owner:
            return True
        effective = expand_permissions(uf.permissions)
        return bool(
            effective
            & (FarmPermission.MANAGE_USERS | FarmPermission.MANAGE_FARM)
        )


def make_farm_permission(perm: FarmPermission) -> type:
    return type(
        f"Can{perm.name.title().replace('_', '')}",
        (HasFarmPermission,),
        {"required_permission": perm},
    )


CanManageReviews = make_farm_permission(FarmPermission.MANAGE_REVIEWS)
CanManageInventory = make_farm_permission(FarmPermission.MANAGE_INVENTORY)
CanManageCycle = make_farm_permission(FarmPermission.MANAGE_CYCLE)
CanManagePond = make_farm_permission(FarmPermission.MANAGE_POND)
CanManageFarm = make_farm_permission(FarmPermission.MANAGE_FARM)
