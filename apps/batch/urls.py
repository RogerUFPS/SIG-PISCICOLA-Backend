from rest_framework.routers import DefaultRouter
from django.urls import path

from .reports.views import BatchProductionReportView
from .views import BatchViewSet, PondBatchViewSet, BatchTransferViewSet

router = DefaultRouter()

urlpatterns = [
    path(
        "farms/<int:farm_pk>/batches/",
        BatchViewSet.as_view(
            {
                "get": "list",
                "post": "create",
            }
        ),
        name="batch-list",
    ),
    path(
        "farms/<int:farm_pk>/batches/<int:pk>/",
        BatchViewSet.as_view(
            {
                "get": "retrieve",
                "patch": "partial_update",
            }
        ),
        name="batch-detail",
    ),
    path(
        "farms/<int:farm_pk>/batches/<int:pk>/set-status/",
        BatchViewSet.as_view({"patch": "set_status"}),
        name="batch-set-status",
    ),
    path(
        "farms/<int:farm_pk>/batches/<int:pk>/split/",
        BatchViewSet.as_view({"post": "split"}),
        name="batch-split",
    ),
    path(
        "farms/<int:farm_pk>/batches/<int:pk>/cycles/",
        BatchViewSet.as_view({"get": "cycles"}),
        name="batch-cycle-list",
    ),
    path(
        "farms/<int:farm_pk>/batches/<int:pk>/traceability/",
        BatchViewSet.as_view({"get": "traceability"}),
        name="batch-traceability",
    ),
    path(
        "farms/<int:farm_pk>/batches/<int:batch_pk>/production-report/",
        BatchProductionReportView.as_view(),
        name="batch-production-report",
    ),
    path(
        "farms/<int:farm_pk>/pond-batches/",
        PondBatchViewSet.as_view(
            {
                "get": "list",
                "post": "create",
            }
        ),
        name="pond-batch-list",
    ),
    path(
        "farms/<int:farm_pk>/pond-batches/<int:pk>/",
        PondBatchViewSet.as_view(
            {
                "get": "retrieve",
                "patch": "partial_update",
            }
        ),
        name="pond-batch-detail",
    ),
    path(
        "farms/<int:farm_pk>/batch-transfers/",
        BatchTransferViewSet.as_view(
            {
                "get": "list",
                "post": "create",
            }
        ),
        name="batch-transfer-list",
    ),
    path(
        "farms/<int:farm_pk>/batch-transfers/<int:pk>/",
        BatchTransferViewSet.as_view({"get": "retrieve"}),
        name="batch-transfer-detail",
    ),
]
