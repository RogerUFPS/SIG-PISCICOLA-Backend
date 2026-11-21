from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from ..accounts.permissions import AdminOr
from ..farms.permissions import IsFarmMember
from .models import Alert, AuditLog, Unit
from .seralizers import (
    AlertSerializer,
    AuditLogFilterSerializer,
    AuditLogSerializer,
    UnitSerializer,
)


class UnitView(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class AuditLogPagination(PageNumberPagination):
    page_size = 50


class AuditLogView(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AdminOr(IsFarmMember)]
    serializer_class = AuditLogSerializer
    permission_app = "core_auditlogs"
    pagination_class = AuditLogPagination

    def get_queryset(self):
        queryset = AuditLog.objects.filter(
            farm_id=self.kwargs["farm_pk"]
        ).select_related("user")
        if self.action != "list":
            return queryset

        query_params = self.request.query_params.copy()
        for field_name in AuditLogFilterSerializer().fields:
            if query_params.get(field_name) == "":
                query_params.pop(field_name)

        filters = AuditLogFilterSerializer(data=query_params)
        filters.is_valid(raise_exception=True)
        values = filters.validated_data

        if "date_from" in values:
            start = timezone.make_aware(
                datetime.combine(values["date_from"], time.min)
            )
            queryset = queryset.filter(created_at__gte=start)
        if "date_to" in values:
            end_date = values["date_to"] + timedelta(days=1)
            end = timezone.make_aware(datetime.combine(end_date, time.min))
            queryset = queryset.filter(created_at__lt=end)
        if "origin" in values:
            queryset = queryset.filter(type_source=values["origin"])
        if "origin_id" in values:
            queryset = queryset.filter(source_id=values["origin_id"])
        if "user" in values:
            user_query = values["user"].strip()
            if user_query.isdecimal():
                queryset = queryset.filter(user_id=int(user_query))
            else:
                user_filter = Q()
                for term in user_query.split():
                    user_filter &= (
                        Q(user__name__icontains=term)
                        | Q(user__lastname__icontains=term)
                        | Q(user__email__icontains=term)
                    )
                queryset = queryset.filter(user_filter)
        if "ip" in values:
            queryset = queryset.filter(ip=values["ip"])
        return queryset


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
