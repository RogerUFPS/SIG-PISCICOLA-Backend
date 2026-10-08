from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from apps.accounts.permissions import AdminOr
from apps.farms.permissions import IsFarmMember, CanManageCycle
from .models import Cycle, CyclePondBatch, ProductionPlan
from .serializers import (
    CyclePondBatchSerializer,
    CycleSerializer,
    ProductionPlanSerializer,
)
from apps.monitoring.services import CycleStateCalculator


class ProductionPlanViewSet(viewsets.ModelViewSet):
    serializer_class = ProductionPlanSerializer

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH", "DELETE"):
            return [AdminOr(CanManageCycle)()]
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        farm_id = self.kwargs.get("farm_pk")
        return ProductionPlan.objects.filter(
            farm_id=farm_id,
            deleted_at__isnull=True,
        ).order_by("-created_at")

    def perform_create(self, serializer):
        farm_id = self.kwargs.get("farm_pk")
        serializer.save(farm_id=farm_id)

    def destroy(self, request, *args, **kwargs):
        plan = self.get_object()
        plan.deleted_at = timezone.now()
        plan.save(update_fields=["deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CycleViewSet(viewsets.ModelViewSet):
    serializer_class = CycleSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["farm_id"] = self.kwargs.get("farm_pk")
        context["pond_id"] = self.kwargs.get("pond_pk")
        return context

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH", "DELETE"):
            return [AdminOr(CanManageCycle)()]
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        farm_id = self.kwargs.get("farm_pk")
        pond_pk = self.kwargs.get("pond_pk")
        
        # Requerir pond_pk - los ciclos SOLO se ven por estanque específico
        if not pond_pk:
            raise ValidationError(
                "Debe especificar un estanque (pond_pk). "
                "Use: /farms/<farm_pk>/ponds/<pond_pk>/cycles/"
            )
        
        queryset = Cycle.objects.filter(
            farm_id=farm_id,
            pond_id=pond_pk,
            deleted_at__isnull=True,
        ).select_related("production_plan", "pond")
        
        # Filtrar por especie si se proporciona
        specie_id = self.request.query_params.get("specie_id")
        if specie_id:
            queryset = queryset.filter(specie_id=specie_id)
        
        # Ordenar por fecha (descendente por defecto, ascendente si se pasa ordering=asc)
        ordering = self.request.query_params.get("ordering", "desc")
        if ordering == "asc":
            queryset = queryset.order_by("start_date")
        else:
            queryset = queryset.order_by("-start_date")
        
        return queryset

    def perform_create(self, serializer):
        farm_id = self.kwargs.get("farm_pk")
        pond_pk = self.kwargs.get("pond_pk")
        serializer.save(farm_id=farm_id, pond_id=pond_pk)

    def destroy(self, request, *args, **kwargs):
        cycle = self.get_object()
        
        # Verificar si hay lotes activos vinculados al ciclo
        active_batches = CyclePondBatch.objects.filter(
            cycle=cycle,
            pond_batch__end_date__isnull=True
        )
        
        if active_batches.exists():
            count = active_batches.count()
            batch_info = []
            for cpb in active_batches[:3]:  # Mostrar hasta 3 lotes
                batch_info.append(f"Lote {cpb.pond_batch.batch.code} en {cpb.pond_batch.pond.code}")
            
            message = f"No se puede borrar este ciclo. Tiene {count} lote(s) activo(s): {', '.join(batch_info)}"
            if count > 3:
                message += f" +{count-3} más"
            
            return Response(
                {"detail": message},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verificar si el ciclo tiene datos de monitoring registrados
        from apps.monitoring.services import CycleStateCalculator
        
        if CycleStateCalculator.has_monitoring_data(cycle.id):
            return Response(
                {
                    "detail": "No se puede eliminar este ciclo. Tiene datos de monitoreo registrados "
                             "(evaluaciones de peces, estadísticas diarias o controles). "
                             "El ciclo puede ser cosechado o cancelado, pero no eliminado completamente."
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        cycle.deleted_at = timezone.now()
        cycle.save(update_fields=["deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def current_state(self, request, farm_pk=None, pond_pk=None, pk=None):
        """
        Retorna el estado actual dinámico del ciclo basado en datos de monitoring.
        
        GET /farms/{farm_pk}/ponds/{pond_pk}/cycles/{pk}/current_state/
        
        Respuesta:
        {
            "fish_quantity": 4850,
            "total_mortality": 150,
            "avg_weight_g": 45.5,
            "min_weight_g": 40.0,
            "max_weight_g": 52.0,
            "mortality_percentage": 3.0,
            "biomass_kg": 220.8,
            "fca": 1.2,
            "days_elapsed": 30,
            "last_evaluation_date": "2026-05-17",
            "has_monitoring_data": true
        }
        """
        cycle = self.get_object()
        state = CycleStateCalculator.get_cycle_current_state(cycle.id)
        return Response(state, status=status.HTTP_200_OK)


class CyclePondBatchViewSet(viewsets.ModelViewSet):
    serializer_class = CyclePondBatchSerializer

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH", "DELETE"):
            return [AdminOr(CanManageCycle)()]
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        farm_id = self.kwargs.get("farm_pk")
        pond_pk = self.kwargs.get("pond_pk")
        cycle_id = self.kwargs.get("cycle_pk")
        
        # Validar que pond_pk y cycle_pk estén presentes
        if not pond_pk or not cycle_id:
            raise ValidationError(
                "Debe especificar estanque (pond_pk) y ciclo (cycle_pk). "
                "Use: /farms/<farm_pk>/ponds/<pond_pk>/cycles/<cycle_pk>/cycle-batches/"
            )
        
        queryset = CyclePondBatch.objects.filter(
            cycle__farm_id=farm_id,
            cycle__pond_id=pond_pk,  # Validar que ciclo está en el estanque correcto
            cycle_id=cycle_id,
        ).select_related(
            "cycle",
            "pond_batch",
            "pond_batch__batch",
            "pond_batch__batch__specie",
            "pond_batch__pond",
        ).order_by("-id")
        
        return queryset

    def perform_create(self, serializer):
        """Al crear un CyclePondBatch, asegurar que sea del mismo estanque del ciclo."""
        farm_id = self.kwargs.get("farm_pk")
        pond_pk = self.kwargs.get("pond_pk")
        cycle_id = self.kwargs.get("cycle_pk")
        
        # Validar que pond_pk y cycle_pk estén presentes
        if not pond_pk or not cycle_id:
            raise ValidationError(
                "Debe especificar estanque (pond_pk) y ciclo (cycle_pk)."
            )
        
        # Obtener ciclo y validar que pertenece al estanque
        try:
            cycle = Cycle.objects.get(id=cycle_id, pond_id=pond_pk, farm_id=farm_id)
        except Cycle.DoesNotExist:
            raise ValidationError(
                "Ciclo no encontrado o no pertenece al estanque/granja especificados."
            )
        
        # La validación de que pond_batch.pond == cycle.pond se ejecutará en el clean() del modelo
        serializer.save(cycle=cycle)
