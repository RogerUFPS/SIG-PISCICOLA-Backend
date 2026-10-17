from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from ..accounts.permissions import AppPermission, IsAdmin
from .models import Alert, AuditLog, Unit
from .seralizers import AlertSerializer, AuditLogSerializer, UnitSerializer


class UnitView(viewsets.ModelViewSet):
    permission_classes = [AllowAny, AppPermission]
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class AuditLogView(viewsets.ModelViewSet):
    permission_classes = [IsAdmin]
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer


from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import AdminOr
from apps.farms.permissions import IsFarmMember


class AlertViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AlertSerializer

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        # Ensure small, on-demand overdue-event alerts exist for this farm so the
        # frontend (polling) sees them immediately without needing external cron.
        try:
            from .utils import ensure_overdue_events_alerts

            ensure_overdue_events_alerts(self.kwargs["farm_pk"])
        except Exception:
            # Defensive: if this check fails, do not break the alerts endpoint.
            pass

        qs = Alert.objects.filter(farm_id=self.kwargs["farm_pk"])

        source_type = self.request.query_params.get("source_type")
        severity = self.request.query_params.get("severity")
        is_resolved = self.request.query_params.get("is_resolved")

        if source_type:
            qs = qs.filter(source_type=source_type)
        if severity:
            qs = qs.filter(severity=severity)
        if is_resolved is not None:
            qs = qs.filter(is_resolved=is_resolved.lower() == "true")

        return qs

    @action(detail=True, methods=["patch"], url_path="resolve")
    def resolve(self, request, farm_pk=None, pk=None):
        alert = self.get_object()
        if alert.is_resolved:
            return Response(
                {"detail": "La alerta ya está resuelta."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.save(update_fields=["is_resolved", "resolved_at", "resolved_by"])
        return Response(AlertSerializer(alert).data)
