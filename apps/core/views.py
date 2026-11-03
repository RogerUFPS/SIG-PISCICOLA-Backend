from rest_framework import viewsets
from rest_framework import mixins
from rest_framework.permissions import AllowAny

from ..accounts.permissions import AdminOr
from ..farms.permissions import IsFarmMember
from .models import Alert, AuditLog, Unit
from .seralizers import AlertSerializer, AuditLogSerializer, UnitSerializer


class UnitView(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class AuditLogView(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AdminOr(IsFarmMember)]
    serializer_class = AuditLogSerializer
    permission_app = "core_auditlogs"

    def get_queryset(self):
        return AuditLog.objects.filter(farm_id=self.kwargs["farm_pk"])


from rest_framework import viewsets


class AlertViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = AlertSerializer
    permission_app = "core_alerts"

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        from .utils import ensure_overdue_events_alerts

        ensure_overdue_events_alerts(self.kwargs["farm_pk"])

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
