# permissions.py
from rest_framework.permissions import BasePermission

from .models import RoleAppPermission

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

        app_parts = view.__class__.__module__.split(".")
        if len(app_parts) < 3 or app_parts[0] != "apps":
            return True
        app = app_parts[1]
        if app == "accounts":
            return True

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
            action = {
                "GET": "can_view",
                "HEAD": "can_view",
                "OPTIONS": "can_view",
                "DELETE": "can_delete",
            }.get(request.method, "can_edit")
        if action is None:
            action = action_by_method.get(request.method)
        if action is None:
            return False

        grant = RoleAppPermission.objects.filter(
            role_id=user.role_id,
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
                CompletionPermission().has_permission(request, view)
                and permission_class().has_permission(request, view)
            )

    return _Permission


class IsAdminOrValid(BasePermission):
    def has_permission(self, request, view):
        return IsAdmin().has_permission(
            request, view
        ) or CompletionPermission().has_permission(request, view)
