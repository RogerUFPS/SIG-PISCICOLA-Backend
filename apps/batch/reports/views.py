from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import AdminOr
from apps.batch.models import Batch
from apps.farms.permissions import IsFarmMember

from .audit import get_client_ip, log_production_report_generation
from .collector import collect_production_report_data
from .constants import FORMAT_PDF, FORMAT_XLSX
from .excel_exporter import export_production_report_xlsx
from .pdf_exporter import export_production_report_pdf
from .serializers import ProductionReportRequestSerializer


def _user_display(user) -> str:
    if not user or not user.is_authenticated:
        return ""

    first_name = getattr(user, "first_name", None)
    last_name = getattr(user, "last_name", None)
    name = f"{first_name or ''} {last_name or ''}".strip()

    if not name:
        name = getattr(user, "name", "")
        lastname = getattr(user, "lastname", "")
        name = f"{name} {lastname}".strip() or name

    return name or getattr(user, "email", None) or str(getattr(user, "pk", ""))


class BatchProductionReportView(APIView):
    """Genera el reporte histórico consolidado de un lote (PDF o Excel)."""

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    @extend_schema(
        request=ProductionReportRequestSerializer,
        responses={
            200: OpenApiResponse(description="Archivo PDF o Excel para descarga"),
            400: OpenApiResponse(description="Parámetros inválidos"),
            404: OpenApiResponse(description="Lote no encontrado"),
            500: OpenApiResponse(description="Error interno al generar el reporte"),
        },
        summary="Generar reporte histórico del proceso productivo",
        description=(
            "Consolida los módulos seleccionados (alimentación, biometría, sanidad, "
            "cosecha, ventas) para un lote. Registra la generación en auditoría. "
            "Los módulos sin datos se indican en el documento."
        ),
    )
    def post(self, request, farm_pk, batch_pk):
        batch = get_object_or_404(Batch, pk=batch_pk, farm_id=farm_pk)

        serializer = ProductionReportRequestSerializer(
            data=request.data,
            context={
                "farm_id": farm_pk,
                "batch_id": batch_pk,
            },
        )
        serializer.is_valid(raise_exception=True)

        modules = serializer.validated_data["modules"]
        export_format = serializer.validated_data["format"]
        cycle_id = serializer.validated_data.get("cycle_id")

        try:
            report_data = collect_production_report_data(
                batch=batch,
                modules=modules,
                cycle_id=cycle_id,
                user_display=_user_display(request.user),
            )
        except AttributeError as exc:
            return Response(
                {
                    "detail": "Error al generar el reporte de producción.",
                    "error": "User model missing expected field",
                    "message": str(exc),
                    "hint": "Revisa el modelo de usuario y los campos usados por el report generator.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            return Response(
                {
                    "detail": "Error interno al generar el reporte de producción.",
                    "error": exc.__class__.__name__,
                    "message": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if export_format == FORMAT_PDF:
            content = export_production_report_pdf(report_data)
            content_type = "application/pdf"
            extension = "pdf"
        else:
            content = export_production_report_xlsx(report_data)
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            extension = "xlsx"

        log_production_report_generation(
            user=request.user,
            farm_id=farm_pk,
            batch_id=batch.id,
            batch_code=batch.code,
            modules=modules,
            export_format=export_format,
            cycle_id=cycle_id,
            empty_modules=report_data["empty_modules"],
            ip=get_client_ip(request),
        )

        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reporte_historico_{batch.code}_{timestamp}.{extension}"

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
