from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404

from apps.accounts.permissions import AdminOr
from apps.farms.permissions import IsFarmMember
from apps.cycle.models import Cycle
from apps.ponds.models import Pond
from .models import FishEvaluated, DailyStat, ControlStat
from .permissions import CanManageMonitoring
from .serializers import (
    FishEvaluatedSerializer,
    DailyStatSerializer,
    ControlStatSerializer,
)


class FishEvaluatedViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar evaluaciones de peces.

    Permisos:
    - GET: IsFarmMember
    - POST/PATCH/DELETE: AdminOr(CanManageMonitoring)
    """
    serializer_class = FishEvaluatedSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()

        farm_pk = self.kwargs.get("farm_pk")
        pond_pk = self.kwargs.get("pond_pk")
        cycle_pk = self.kwargs.get("cycle_pk")

        # Evita errores en la generación de esquema (swagger) sin kwargs
        if farm_pk and pond_pk and cycle_pk:
            ctx["pond"] = get_object_or_404(Pond, id=pond_pk, farm_id=farm_pk)
            ctx["cycle"] = get_object_or_404(
                Cycle,
                id=cycle_pk,
                farm_id=farm_pk,
                pond_id=pond_pk,
                deleted_at__isnull=True,
            )
        return ctx

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH", "DELETE"):
            return [AdminOr(CanManageMonitoring)()]
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        farm_id = self.kwargs.get("farm_pk")
        pond_pk = self.kwargs.get("pond_pk")
        cycle_id = self.kwargs.get("cycle_pk")
        
        if not pond_pk or not cycle_id:
            raise ValidationError(
                "Debe especificar estanque (pond_pk) y ciclo (cycle_pk). "
                "Use: /farms/<farm_pk>/ponds/<pond_pk>/cycles/<cycle_pk>/fish-evaluations/"
            )

        qs = FishEvaluated.objects.filter(
            cycle__farm_id=farm_id,
            cycle__pond_id=pond_pk,
            cycle_id=cycle_id,
            deleted_at__isnull=True,
        ).select_related("cycle", "pond")

        return qs.order_by("-evaluation_date")

    def perform_create(self, serializer):
        cycle_id = self.kwargs.get("cycle_pk")
        pond_pk = self.kwargs.get("pond_pk")
        serializer.save(cycle_id=cycle_id, pond_id=pond_pk)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        deleted_at = timezone.now()

        serializer = self.get_serializer(obj)
        if obj.mortality_quantity > 0:
            serializer._apply_mortality_stock_change(
                cycle=obj.cycle,
                pond=obj.pond,
                quantity=obj.mortality_quantity,
                restore=True,
            )

        obj.deleted_at = deleted_at
        obj.save(update_fields=["deleted_at"])

        remaining_evaluation = (
            FishEvaluated.objects.filter(
                cycle=obj.cycle,
                pond=obj.pond,
                evaluation_date=obj.evaluation_date,
                deleted_at__isnull=True,
            )
            .exclude(pk=obj.pk)
            .order_by("-updated_at")
            .first()
        )
        if remaining_evaluation:
            serializer._refresh_cycle_control_stat(
                remaining_evaluation, ignore_same_day=True
            )
        else:
            ControlStat.objects.filter(
                cycle=obj.cycle,
                pond=obj.pond,
                control_date=obj.evaluation_date,
                deleted_at__isnull=True,
            ).update(deleted_at=deleted_at)

        return Response(status=status.HTTP_204_NO_CONTENT)


class DailyStatViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar estadísticas diarias.

    Permisos:
    - GET: IsFarmMember
    - POST/PATCH/DELETE: AdminOr(CanManageMonitoring)
    """
    serializer_class = DailyStatSerializer

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH", "DELETE"):
            return [AdminOr(CanManageMonitoring)()]
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        farm_id = self.kwargs.get("farm_pk")
        pond_pk = self.kwargs.get("pond_pk")
        cycle_id = self.kwargs.get("cycle_pk")
        
        qs = DailyStat.objects.filter(
            cycle__farm_id=farm_id,
            deleted_at__isnull=True,
        ).select_related("cycle", "pond").prefetch_related("product_usages")

        # Si viene cycle_pk en URL, validar pond_pk también
        if cycle_id:
            if not pond_pk:
                raise ValidationError(
                    "Debe especificar estanque (pond_pk). "
                    "Use: /farms/<farm_pk>/ponds/<pond_pk>/cycles/<cycle_pk>/daily-stats/"
                )
            qs = qs.filter(cycle_id=cycle_id, cycle__pond_id=pond_pk)
        # Si no viene cycle_pk, es lista por granja (sin validación de pond)

        return qs.order_by("-stat_date", "-created_at")

    def perform_create(self, serializer):
        cycle_id = self.kwargs.get("cycle_pk")
        pond_pk = self.kwargs.get("pond_pk")
        serializer.save(cycle_id=cycle_id, pond_id=pond_pk)

    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()
        obj.deleted_at = timezone.now()
        obj.save(update_fields=["deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ControlStatViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para LEER estadísticas de control (READ-ONLY).

    ControlStat se genera AUTOMÁTICAMENTE cada vez que se crea un FishEvaluated.
    El frontend solo puede listar/consultar, no crear/editar/eliminar.

    Permisos:
    - GET: IsFarmMember
    """
    serializer_class = ControlStatSerializer

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        farm_id = self.kwargs.get("farm_pk")
        pond_pk = self.kwargs.get("pond_pk")
        cycle_id = self.kwargs.get("cycle_pk")

        qs = ControlStat.objects.filter(
            cycle__farm_id=farm_id,
            deleted_at__isnull=True,
        ).select_related("cycle", "pond")

        # Si viene cycle_pk en URL, validar pond_pk también
        if cycle_id:
            if not pond_pk:
                raise ValidationError(
                    "Debe especificar estanque (pond_pk). "
                    "Use: /farms/<farm_pk>/ponds/<pond_pk>/cycles/<cycle_pk>/control-stats/"
                )
            qs = qs.filter(cycle_id=cycle_id, cycle__pond_id=pond_pk)
        # Si no viene cycle_pk, es lista por granja (sin validación de pond)

        return qs.order_by("-control_date")
        return Response(status=status.HTTP_204_NO_CONTENT)


__all__ = [
    "FishEvaluatedViewSet",
    "DailyStatViewSet",
    "ControlStatViewSet",
]
