# views.py
from rest_framework import status, viewsets
from rest_framework.response import Response

from apps.accounts.permissions import AdminOr
from apps.farms.permissions import CanManageInventory, IsFarmMember

from .models import Buy, InventoryMovement
from .serializers import BuySerializer, InventoryMovementSerializer
from .utils import _delete_details_with_movements


class BuyViewSet(viewsets.ModelViewSet):
    serializer_class = BuySerializer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AdminOr(IsFarmMember)()]
        return [AdminOr(CanManageInventory)()]

    def get_queryset(self):
        qs = (
            Buy.objects.filter(farm_id=self.kwargs["farm_pk"])
            .prefetch_related("details")
            .order_by("-date")
        )
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        supplier = self.request.query_params.get("supplier_id")

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if supplier:
            qs = qs.filter(supplier_id=supplier)

        return qs

    def perform_create(self, serializer):
        serializer.save(farm_id=self.kwargs["farm_pk"])

    def destroy(self, request, *args, **kwargs):
        buy = self.get_object()
        _delete_details_with_movements(buy)
        buy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InventoryMovementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InventoryMovementSerializer

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    def get_queryset(self):
        qs = InventoryMovement.objects.filter(
            farm_id=self.kwargs["farm_pk"]
        ).select_related("product")
        product_id = self.request.query_params.get("product_id")
        movement_type = self.request.query_params.get("movement_type")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if product_id:
            qs = qs.filter(product_id=product_id)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return qs
