# urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (CityListView, DepartmentListView, FarmRoleViewSet,
                    FarmViewSet, UserFarmViewSet)

router = DefaultRouter()
router.register(r"farms", FarmViewSet, basename="farm")

farm_router = DefaultRouter()
farm_router.register(r"roles", FarmRoleViewSet, basename="farm-role")
farm_router.register(r"members", UserFarmViewSet, basename="farm-member")

urlpatterns = [
    path("", include(router.urls)),
    path("farms/<int:farm_pk>/", include(farm_router.urls)),
    path("departments/", DepartmentListView.as_view()),
    path("cities/", CityListView.as_view()),
]
