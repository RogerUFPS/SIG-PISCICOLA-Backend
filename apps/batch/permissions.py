from rest_framework.permissions import BasePermission

from apps.accounts.permissions import AppPermission


class CanManageBatch(BasePermission):
    def has_permission(self, request, view):
        return AppPermission().has_permission(request, view)
