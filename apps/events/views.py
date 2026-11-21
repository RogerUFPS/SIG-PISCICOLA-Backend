from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import AdminOr
from apps.farms.permissions import IsFarmMember
from .models import GradingEvent
from .permissions import CanManageEvent
from .serializers import GradingEventSerializer


class GradingEventViewSet(viewsets.ViewSet):
    serializer_class = GradingEventSerializer

    def get_permissions(self):
        if self.request.method in ("POST", "PATCH"):
            return [AdminOr(CanManageEvent)()]
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        farm_id = self.kwargs.get("farm_pk")
        return GradingEvent.objects.filter(
            cycle__farm_id=farm_id
        ).select_related("cycle", "source_pond_batch", "to_pond_batch").order_by("-date")

    def create(self, request, farm_pk=None):
        return Response(
            {
                "detail": (
                    "Los movimientos de peces entre estanques no se realizan "
                    "manualmente durante un ciclo."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def list(self, request, farm_pk=None):
        queryset = self.get_queryset()
        serializer = GradingEventSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, farm_pk=None, pk=None):
        event = self.get_queryset().filter(pk=pk).first()
        if event is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        serializer = GradingEventSerializer(event)
        return Response(serializer.data)
