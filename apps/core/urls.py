from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AlertViewSet, AuditLogView, UnitView

farm_router = DefaultRouter()
farm_router.register(r"alerts", AlertViewSet, basename="alert")

global_router = DefaultRouter()
global_router.register(r"unit", UnitView, basename="unit")
farm_router.register(r"auditlogs", AuditLogView, basename="auditlog")

urlpatterns = [
    path("farms/core/<int:farm_pk>/", include(farm_router.urls)),
    path("", include(global_router.urls)),
]
