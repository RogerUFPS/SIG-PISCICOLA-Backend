# views.py

from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import AdminOr
from apps.farms.permissions import CanManageCycle, IsFarmMember

from .models import Harvest, HarvestClassification
from .serializers import (BatchFromClassificationSerializer,
                          HarvestClassificationSerializer,
                          HarvestDetailSerializer, HarvestSerializer)
from .utils import create_batch_from_classification


class HarvestListCreateView(generics.ListCreateAPIView):
    serializer_class = HarvestSerializer

    def get_permissions(self):
        if self.request.method == "GET":
            return [AdminOr(IsFarmMember)()]
        return [AdminOr(CanManageCycle)()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["farm_pk"] = self.kwargs["farm_pk"]
        context["farm_id"] = self.kwargs["farm_pk"]
        context["created_by"] = self.request.user
        return context

    def perform_create(self, serializer):
        cycle = serializer.validated_data["cycle"]

        if cycle.farm_id != self.kwargs["farm_pk"]:
            raise ValidationError({"cycle": "El ciclo no pertenece a esta granja."})

        serializer.save(
            farm_id=self.kwargs["farm_pk"],
            created_by=self.request.user,
        )

    def get_queryset(self):
        qs = (
            Harvest.objects.filter(
                farm_id=self.kwargs["farm_pk"],
            )
            .prefetch_related(
                "classifications__sources__cycle_pond_batch__pond_batch__batch",
                "classifications__derivations",
                "sources__cycle_pond_batch__pond_batch__batch",
            )
            .order_by("-date")
        )

        cycle_id = self.request.query_params.get("cycle_id")
        harvest_type = self.request.query_params.get("type")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)
        if harvest_type:
            qs = qs.filter(type=harvest_type)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        return qs


class HarvestDetailView(generics.RetrieveAPIView):
    serializer_class = HarvestDetailSerializer
    permission_classes = [AdminOr(IsFarmMember)]

    def get_queryset(self):
        return Harvest.objects.filter(
            farm_id=self.kwargs["farm_pk"],
        ).prefetch_related(
            "classifications__sources__cycle_pond_batch__pond_batch__batch",
            "classifications__derivations",
            "sources__cycle_pond_batch__pond_batch__batch",
        )


class HarvestClassificationListView(generics.ListAPIView):
    serializer_class = HarvestClassificationSerializer
    permission_classes = [AdminOr(IsFarmMember)]

    def get_queryset(self):
        return HarvestClassification.objects.filter(
            farm_id=self.kwargs["farm_pk"],
            harvest_id=self.kwargs["harvest_pk"],
        ).prefetch_related(
            "sources__cycle_pond_batch__pond_batch__batch",
            "derivations",
        )


class BatchFromClassificationView(APIView):
    serializer_class = BatchFromClassificationSerializer
    permission_classes = [AdminOr(CanManageCycle)]

    def post(self, request, farm_pk, harvest_pk, classification_pk):
        try:
            classification = (
                HarvestClassification.objects.select_related("harvest__cycle")
                .prefetch_related(
                    "sources__cycle_pond_batch__pond_batch__batch",
                    "harvest__sources__cycle_pond_batch__pond_batch__batch",
                )
                .get(
                    pk=classification_pk,
                    harvest_id=harvest_pk,
                    farm_id=farm_pk,
                )
            )
        except HarvestClassification.DoesNotExist:
            return Response(
                {"detail": "Clasificación no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = BatchFromClassificationSerializer(
            data=request.data,
            context={
                "farm_id": farm_pk,
                "classification": classification,
            },
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "min_weight_g" not in data or data.get("min_weight_g") is None:
            harvest = classification.harvest
            data["min_weight_g"] = float(harvest.min_weight_g)
            data["avg_weight_g"] = float(harvest.avg_weight_g)
            data["max_weight_g"] = float(harvest.max_weight_g)

        fish_count = data.pop("fish_count", None)

        try:
            batch = create_batch_from_classification(
                classification=classification,
                fish_count=fish_count,
                created_by=request.user,
                **data,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "detail": "Lote creado correctamente.",
                "batch_id": batch.id,
                "fish_count": batch.initial_quantity,
            },
            status=status.HTTP_201_CREATED,
        )
