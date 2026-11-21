from rest_framework.permissions import BasePermission

from apps.accounts.permissions import CompletionPermission, IsAdmin


class SpeciePermission(BasePermission):
    def has_permission(self, request, view):
        return IsAdmin().has_permission(
            request, view
        ) or CompletionPermission().has_permission(request, view)
