# urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BuyViewSet, InventoryMovementViewSet

farm_router = DefaultRouter()
farm_router.register(r"buys", BuyViewSet, basename="farm-buy")
farm_router.register(
    r"inventory-movements", InventoryMovementViewSet, basename="farm-inventory-movement"
)

urlpatterns = [
    path("farms/<int:farm_pk>/", include(farm_router.urls)),
]
