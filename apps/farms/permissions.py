from rest_framework.permissions import BasePermission

from apps.accounts.permissions import ROLE_ADMIN

from .models import UserFarm


def _get_farm_pk(view, request=None):
    kwargs = getattr(view, "kwargs", {}) or {}
    farm_pk = kwargs.get("farm_pk") or kwargs.get("farm_id")
    if farm_pk is None and view.__class__.__name__ == "FarmViewSet":
        farm_pk = kwargs.get("pk")
    if farm_pk is not None or request is None:
        return farm_pk
    request_data = getattr(request, "data", {}) or {}
    query_params = getattr(request, "query_params", getattr(request, "GET", {})) or {}
    return request_data.get("farm_id") or query_params.get("farm_id")


def _get_user_farm(user, farm_pk) -> UserFarm | None:
    if not user.is_authenticated:
        return None
    try:
        uf = UserFarm.objects.select_related("farm", "farm_role").get(
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
        from apps.accounts.permissions import AppPermission

        return AppPermission().has_permission(request, view)


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
        from apps.accounts.permissions import AppPermission

        return AppPermission().has_permission(request, view)


class CanManageReviews(HasFarmPermission):
    pass


class CanManageInventory(HasFarmPermission):
    pass


class CanManageCycle(HasFarmPermission):
    pass


class CanManagePond(HasFarmPermission):
    pass


class CanManageFarm(HasFarmPermission):
    pass
