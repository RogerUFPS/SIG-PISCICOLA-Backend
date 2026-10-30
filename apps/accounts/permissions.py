# permissions.py
from rest_framework.permissions import BasePermission

ROLE_ADMIN = "Admin"
ROLE_PRODUCTOR = "Productor"
ROLE_OPERARIO = "Operario"

ALLOWED_PATH_PREFIXES = (
    "/api/users/me/complete/",
    "/api/auth/logout/",
    "/api/invitations/",
)


class RolePermission(BasePermission):
    role_name = None

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role.name == self.role_name
        )


class CompletionPermission(BasePermission):
    message = "Debes completar tu perfil antes de continuar."

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if any(request.path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
            return True

        if user.is_temp_password:
            return request.path.startswith("/api/auth/change-password/")

        if not user.is_profile_complete:
            return False

        return AppPermission().has_permission(request, view)


class AppPermission(BasePermission):
    message = "Tu rol no tiene permisos para esta operación en la aplicación."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return request.method in ("GET", "HEAD", "OPTIONS")
        if getattr(getattr(user, "role", None), "name", None) == ROLE_ADMIN:
            return True

        request_data = getattr(request, "data", {})
        query_params = getattr(request, "query_params", getattr(request, "GET", {}))
        farm_id = (
            view.kwargs.get("farm_pk")
            or view.kwargs.get("farm_id")
            or request_data.get("farm_id")
            or query_params.get("farm_id")
        )
        if farm_id is None:
            if request.method in ("GET", "HEAD", "OPTIONS"):
                return True
            return view.__class__.__module__.startswith("apps.accounts.")

        from apps.farms.models import FarmRoleAppPermission, UserFarm

        membership = UserFarm.objects.select_related("farm_role").filter(
            user=user,
            farm_id=farm_id,
            farm__deleted_at__isnull=True,
        ).first()
        if membership is None or (
            not membership.is_owner
            and membership.status != UserFarm.Status.ACTIVE
        ):
            return False
        if membership.is_owner:
            return True
        if getattr(view, "permission_app", None) == "farm_users":
            from apps.farms.enums import (
                FarmPermission,
                effective_farm_permissions,
            )

            return bool(
                effective_farm_permissions(membership)
                & (FarmPermission.MANAGE_USERS | FarmPermission.MANAGE_FARM)
            )
        if membership.farm_role_id is not None and (
            membership.farm_role.deleted_at is not None
            or membership.farm_role.farm_id != membership.farm_id
        ):
            return False

        app = getattr(view, "permission_app", None)
        if app is None:
            app_parts = view.__class__.__module__.split(".")
            if len(app_parts) < 3 or app_parts[0] != "apps":
                return False
            app = app_parts[1]

        from apps.farms.enums import FarmPermission, effective_farm_permissions

        legacy_permissions_by_app = {
            "batch": FarmPermission.MANAGE_CYCLE,
            "cycle": FarmPermission.MANAGE_CYCLE,
            "events": FarmPermission.MANAGE_CYCLE,
            "feeding": FarmPermission.MANAGE_CYCLE,
            "harvest": FarmPermission.MANAGE_CYCLE,
            "health": FarmPermission.MANAGE_REVIEWS,
            "monitoring": FarmPermission.MANAGE_REVIEWS,
            "ponds": FarmPermission.MANAGE_POND,
            "products": FarmPermission.MANAGE_INVENTORY,
            "purchases": FarmPermission.MANAGE_INVENTORY,
            "sales": FarmPermission.MANAGE_INVENTORY,
            "farms": FarmPermission.MANAGE_FARM,
        }
        legacy_permission = legacy_permissions_by_app.get(app)
        if (
            legacy_permission is not None
            and effective_farm_permissions(membership) & legacy_permission
        ):
            return True

        if membership.farm_role_id is None:
            return False

        action_by_method = {
            "GET": "can_view",
            "HEAD": "can_view",
            "OPTIONS": "can_view",
            "POST": "can_create",
            "PUT": "can_edit",
            "PATCH": "can_edit",
            "DELETE": "can_delete",
        }
        view_action = getattr(view, "action", None)
        action = {
            "list": "can_view",
            "retrieve": "can_view",
            "create": "can_create",
            "update": "can_edit",
            "partial_update": "can_edit",
            "destroy": "can_delete",
        }.get(view_action)
        if action is None and view_action:
            action = action_by_method.get(request.method)
        if action is None:
            action = action_by_method.get(request.method)
        if action is None:
            return False

        grant = FarmRoleAppPermission.objects.filter(
            role_id=membership.farm_role_id,
            app=app,
        ).first()
        return bool(grant and grant.can_view and getattr(grant, action))


class IsAdmin(RolePermission):
    role_name = ROLE_ADMIN


class IsProductor(RolePermission):
    role_name = ROLE_PRODUCTOR


class IsOperario(RolePermission):
    role_name = ROLE_OPERARIO


def AdminOr(permission_class):
    class _Permission(BasePermission):
        def has_permission(self, request, view):
            return IsAdmin().has_permission(request, view) or (
                request.user.is_authenticated
                and request.user.is_profile_complete
                and not request.user.is_temp_password
                and permission_class().has_permission(request, view)
            )

    return _Permission


class IsAdminOrValid(BasePermission):
    def has_permission(self, request, view):
        return IsAdmin().has_permission(
            request, view
        ) or CompletionPermission().has_permission(request, view)
