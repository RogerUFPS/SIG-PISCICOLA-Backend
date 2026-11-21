from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProductViewSet, SupplierViewSet, TypeProductViewSet

catalog_router = DefaultRouter()
catalog_router.register(r"type-products", TypeProductViewSet, basename="type-product")

farm_router = DefaultRouter()
farm_router.register(r"products", ProductViewSet, basename="farm-product")
farm_router.register(r"suppliers", SupplierViewSet, basename="farm-supplier")
urlpatterns = [
    path("", include(catalog_router.urls)),
    path("farms/<int:farm_pk>/", include(farm_router.urls)),
]
