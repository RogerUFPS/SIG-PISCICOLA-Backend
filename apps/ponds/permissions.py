from rest_framework.permissions import BasePermission

from apps.accounts.permissions import CompletionPermission, IsAdmin
from apps.farms.permissions import IsFarmMember
from .models import UserFarmPond


class IsPondMember(BasePermission):
    def has_permission(self, request, view):
        if not CompletionPermission().has_permission(request, view):
            return False
        pond_id = view.kwargs.get("pond_id")
        farm_id = view.kwargs.get("farm_id")
        if not pond_id or not farm_id:
            return False

        return UserFarmPond.objects.filter(
            user=request.user,
            pond_id=pond_id,
            farm_id=farm_id,
        ).exists()


class PondDetailPermission(BasePermission):
    def has_permission(self, request, view):
        is_admin = IsAdmin().has_permission(request, view)
        is_farm_member = CompletionPermission().has_permission(
            request, view
        ) and IsFarmMember().has_permission(request, view)

        if request.method == "GET":
            return is_admin or is_farm_member or IsPondMember().has_permission(
                request, view
            )

        return is_admin or is_farm_member


class IsActiveFarmMember(BasePermission):
    def has_permission(self, request, view):
        if not CompletionPermission().has_permission(request, view):
            return False
        farm_id = view.kwargs.get("farm_id")
        if not farm_id:
            return False
        from apps.farms.models import UserFarm

        return UserFarm.objects.filter(
            user=request.user,
            farm_id=farm_id,
            status=UserFarm.Status.ACTIVE,
        ).exists()


class PondListPermission(BasePermission):
    def has_permission(self, request, view):
        is_admin = IsAdmin().has_permission(request, view)
        is_farm_member = CompletionPermission().has_permission(
            request, view
        ) and IsFarmMember().has_permission(request, view)
        if request.method == "GET":
            return is_admin or is_farm_member
        return is_admin or is_farm_member
