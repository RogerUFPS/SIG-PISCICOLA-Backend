from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import AdminOr
from apps.farms.models import Farm
from apps.farms.permissions import CanManageInventory
from apps.harvest.models import HarvestClassification

from .models import SaleDetail
from .serializers import (ClientCreateSerializer, ClientDetailSerializer,
                          ClientListSerializer, ClientUpdateSerializer,
                          SaleCreateSerializer, SaleDetailListSerializer,
                          SaleDetailSerializer, SaleDetailUpdateSerializer,
                          SaleListSerializer, SaleUpdateSerializer)
from .utils import (EDIT_WINDOW_MINUTES, _get_detail_or_404, can_delete_client,
                    create_client, create_full_sale, delete_client, edit_sale,
                    edit_sale_detail, get_client, get_sale, list_clients,
                    list_sale_details_by_sale, list_sales, list_sales_client,
                    list_sales_harvest_classification, update_client,
                    update_sale_observations)


class _SaleItemInputSerializer(drf_serializers.ModelSerializer):
    class Meta:
        model = SaleDetail
        fields = ["harvest_classification", "quantity_g", "fish_count", "price"]

    def validate_quantity_g(self, value):
        if value <= 0:
            raise drf_serializers.ValidationError("La cantidad debe ser mayor a cero.")
        return value

    def validate_fish_count(self, value):
        if value is not None and value <= 0:
            raise drf_serializers.ValidationError(
                "La cantidad de peces debe ser mayor a cero."
            )
        return value

    def validate_price(self, value):
        if value < 0:
            raise drf_serializers.ValidationError(
                "El precio total no puede ser negativo."
            )
        return value


def _edit_window_payload(reference_dt) -> dict:
    deadline = reference_dt + timedelta(minutes=EDIT_WINDOW_MINUTES)
    return {
        "can_edit": timezone.now() <= deadline,
        "window_minutes": EDIT_WINDOW_MINUTES,
        "deadline": deadline.isoformat(),
    }


class ClientListCreateView(APIView):
    serializer_class = ClientCreateSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int) -> Response:
        qp = request.query_params
        filters = {
            "farm_id": farm_pk,
            **{
                k: qp.get(k)
                for k in ("client_type", "document_type", "search")
                if qp.get(k) is not None
            },
        }
        return Response(ClientListSerializer(list_clients(filters), many=True).data)

    def post(self, request: Request, farm_pk: int) -> Response:
        farm = get_object_or_404(Farm, pk=farm_pk)
        serializer = ClientCreateSerializer(
            data=request.data,
            context={"farm": farm},
        )
        serializer.is_valid(raise_exception=True)
        client = create_client({**serializer.validated_data, "farm": farm})
        return Response(
            ClientDetailSerializer(client).data, status=status.HTTP_201_CREATED
        )


class ClientRetrieveUpdateDestroyView(APIView):
    serializer_class = ClientDetailSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int, pk: int) -> Response:
        client = get_client(pk, farm_id=farm_pk)
        return Response(ClientDetailSerializer(client).data)

    def patch(self, request: Request, farm_pk: int, pk: int) -> Response:
        client = get_client(pk, farm_id=farm_pk)
        serializer = ClientUpdateSerializer(client, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = update_client(pk, serializer.validated_data)
        return Response(ClientDetailSerializer(updated).data)

    def delete(self, request: Request, farm_pk: int, pk: int) -> Response:
        get_client(pk, farm_id=farm_pk)
        delete_client(pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClientCanDeleteView(APIView):
    serializer_class = ClientDetailSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int, pk: int) -> Response:
        get_client(pk, farm_id=farm_pk)
        can_delete = can_delete_client(pk)
        return Response(
            {
                "can_delete": can_delete,
                "reason": (
                    None
                    if can_delete
                    else "El cliente tiene ventas asociadas y no puede eliminarse."
                ),
            }
        )


class SaleListView(APIView):
    serializer_class = SaleListSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int) -> Response:
        qp = request.query_params
        filters = {
            "farm_id": farm_pk,
            **{
                k: qp.get(k)
                for k in (
                    "client_id",
                    "payment_method",
                    "date_from",
                    "date_to",
                    "invoice_number",
                )
                if qp.get(k) is not None
            },
        }
        return Response(SaleListSerializer(list_sales(filters), many=True).data)


class FullSaleCreateView(APIView):
    serializer_class = SaleCreateSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def post(self, request: Request, farm_pk: int) -> Response:
        farm = get_object_or_404(Farm, pk=farm_pk)

        raw_details = request.data.get("details", [])
        if not isinstance(raw_details, list):
            return Response(
                {"details": "Se esperaba una lista de detalles."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sale_input = {k: v for k, v in request.data.items() if k != "details"}
        sale_ser = SaleCreateSerializer(data=sale_input, context={"farm": farm})
        sale_ser.is_valid(raise_exception=True)

        detail_errors: dict = {}
        detail_sers: list[_SaleItemInputSerializer] = []
        for idx, item in enumerate(raw_details):
            ser = _SaleItemInputSerializer(data=item)
            if ser.is_valid():
                detail_sers.append(ser)
            else:
                detail_errors[f"details[{idx}]"] = ser.errors

        if detail_errors:
            return Response(detail_errors, status=status.HTTP_400_BAD_REQUEST)

        for idx, ser in enumerate(detail_sers):
            hc: HarvestClassification = ser.validated_data["harvest_classification"]
            if hc.farm_id != farm_pk:
                return Response(
                    {
                        f"details[{idx}]": {
                            "harvest_classification": (
                                f"La clasificación de cosecha {hc.pk} "
                                "no pertenece a esta finca."
                            )
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        details_data = [{**ser.validated_data, "farm": farm} for ser in detail_sers]

        sale = create_full_sale(
            sale_data={**sale_ser.validated_data, "farm": farm},
            details_data=details_data,
            created_by=request.user,
        )
        return Response(SaleDetailSerializer(sale).data, status=status.HTTP_201_CREATED)


class SaleRetrieveView(APIView):
    serializer_class = SaleDetailSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int, pk: int) -> Response:
        sale = get_sale(pk, farm_id=farm_pk)
        return Response(SaleDetailSerializer(sale).data)


class SaleEditView(APIView):
    serializer_class = SaleUpdateSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def patch(self, request: Request, farm_pk: int, pk: int) -> Response:
        sale = get_sale(pk, farm_id=farm_pk)
        serializer = SaleUpdateSerializer(sale, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = edit_sale(pk, serializer.validated_data)
        return Response(SaleDetailSerializer(updated).data)


class SaleObservationsView(APIView):
    serializer_class = SaleUpdateSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def patch(self, request: Request, farm_pk: int, pk: int) -> Response:
        observations = request.data.get("observations")
        if observations is None:
            return Response(
                {"observations": "Este campo es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(observations, str):
            return Response(
                {"observations": "Se esperaba una cadena de texto."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        get_sale(pk, farm_id=farm_pk)
        sale = update_sale_observations(pk, observations)
        return Response(SaleDetailSerializer(sale).data)


class SaleCanEditView(APIView):
    serializer_class = SaleDetailSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int, pk: int) -> Response:
        sale = get_sale(pk, farm_id=farm_pk)
        return Response(_edit_window_payload(sale.created_at))


class SalesByClientView(APIView):
    serializer_class = SaleListSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int, client_id: int) -> Response:
        get_client(client_id, farm_id=farm_pk)
        sales = list_sales_client(client_id, farm_id=farm_pk)
        return Response(SaleListSerializer(sales, many=True).data)


class SalesByHarvestClassificationView(APIView):
    serializer_class = SaleDetailSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int, hc_id: int) -> Response:
        get_object_or_404(HarvestClassification, pk=hc_id, farm_id=farm_pk)
        sales = list_sales_harvest_classification(hc_id, farm_id=farm_pk)
        return Response(SaleDetailSerializer(sales, many=True).data)


class SaleDetailsBySaleView(APIView):
    serializer_class = SaleDetailListSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int, sale_id: int) -> Response:
        get_sale(sale_id, farm_id=farm_pk)
        details = list_sale_details_by_sale(sale_id)
        return Response(SaleDetailListSerializer(details, many=True).data)


class SaleDetailEditView(APIView):
    serializer_class = SaleDetailUpdateSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def patch(self, request: Request, farm_pk: int, pk: int) -> Response:
        detail = _get_detail_or_404(pk)
        if detail.farm_id != farm_pk:
            raise ValidationError({"detail": "Detalle de venta no encontrado."})
        serializer = SaleDetailUpdateSerializer(detail, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = edit_sale_detail(pk, serializer.validated_data)
        return Response(SaleDetailListSerializer(updated).data)


class SaleDetailCanEditView(APIView):
    serializer_class = SaleDetailListSerializer
    permission_classes = [AdminOr(CanManageInventory)]

    def get(self, request: Request, farm_pk: int, pk: int) -> Response:
        detail = _get_detail_or_404(pk)
        if detail.farm_id != farm_pk:
            raise ValidationError({"detail": "Detalle de venta no encontrado."})
        return Response(_edit_window_payload(detail.sale.created_at))
