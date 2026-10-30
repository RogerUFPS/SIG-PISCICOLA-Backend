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


LEGACY_PERMISSIONS_BY_APP = None
ACTION_BY_METHOD = {
    "GET": "can_view",
    "HEAD": "can_view",
    "OPTIONS": "can_view",
    "POST": "can_create",
    "PUT": "can_edit",
    "PATCH": "can_edit",
    "DELETE": "can_delete",
}
ACTION_BY_VIEW = {
    "list": "can_view",
    "retrieve": "can_view",
    "create": "can_create",
    "update": "can_edit",
    "partial_update": "can_edit",
    "destroy": "can_delete",
}


def _legacy_permissions_by_app():
    global LEGACY_PERMISSIONS_BY_APP
    if LEGACY_PERMISSIONS_BY_APP is None:
        from apps.farms.enums import FarmPermission

        LEGACY_PERMISSIONS_BY_APP = {
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
    return LEGACY_PERMISSIONS_BY_APP


def _permission_app(view):
    app = getattr(view, "permission_app", None)
    if app is not None:
        return app
    app_parts = view.__class__.__module__.split(".")
    if len(app_parts) < 3 or app_parts[0] != "apps":
        return None
    return app_parts[1]


def _permission_action(request, view):
    view_action = getattr(view, "action", None)
    action = ACTION_BY_VIEW.get(view_action)
    if action is None:
        action = ACTION_BY_METHOD.get(request.method)
    return action


def _grant_allows(grant, action):
    return bool(grant and grant.can_view and getattr(grant, action, False))


def _membership_allows_app(membership, view, app, action):
    from apps.farms.enums import FarmPermission, effective_farm_permissions
    from apps.farms.models import FarmRoleAppPermission

    if membership.is_owner:
        return True
    if app == "farm_users" or getattr(view, "permission_app", None) == "farm_users":
        return bool(
            effective_farm_permissions(membership)
            & (FarmPermission.MANAGE_USERS | FarmPermission.MANAGE_FARM)
        )
    farm_role = getattr(membership, "farm_role", None)
    if membership.farm_role_id is not None and (
        farm_role is None
        or farm_role.deleted_at is not None
        or farm_role.farm_id != membership.farm_id
    ):
        return False
    if app == "farms" and action == "can_view":
        return True

    grant = None
    if membership.farm_role_id is not None:
        grant = FarmRoleAppPermission.objects.filter(
            role_id=membership.farm_role_id,
            app=app,
        ).first()

    if farm_role is not None and farm_role.permissions_configured:
        return _grant_allows(grant, action)

    legacy_permission = _legacy_permissions_by_app().get(app)
    if (
        legacy_permission is not None
        and effective_farm_permissions(membership) & legacy_permission
    ):
        return True
    return _grant_allows(grant, action)


class AppPermission(BasePermission):
    message = "Tu rol no tiene permisos para esta operación en la aplicación."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return request.method in ("GET", "HEAD", "OPTIONS")
        if getattr(getattr(user, "role", None), "name", None) == ROLE_ADMIN:
            return True

        from apps.farms.permissions import _get_farm_pk

        farm_id = _get_farm_pk(view, request)
        app = _permission_app(view)
        action = _permission_action(request, view)
        if action is None or app is None:
            return False

        from apps.farms.models import UserFarm

        memberships = UserFarm.objects.select_related("farm_role").filter(
            user=user,
            farm__deleted_at__isnull=True,
        )
        if farm_id is not None:
            memberships = memberships.filter(farm_id=farm_id)

        memberships = [
            membership
            for membership in memberships
            if membership.is_owner or membership.status == UserFarm.Status.ACTIVE
        ]
        if farm_id is not None:
            if not memberships:
                return False
            return _membership_allows_app(memberships[0], view, app, action)

        if action == "can_view":
            return True
        if view.__class__.__module__.startswith("apps.accounts."):
            return True
        return any(
            _membership_allows_app(membership, view, app, action)
            for membership in memberships
        )


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
