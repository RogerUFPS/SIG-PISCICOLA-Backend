from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import GradingEventViewSet

router = DefaultRouter()

urlpatterns = [
    path(
        "farms/<int:farm_pk>/grading-events/",
        GradingEventViewSet.as_view(
            {
                "get": "list",
                "post": "create",
            }
        ),
        name="grading-event-list",
    ),
    path(
        "farms/<int:farm_pk>/grading-events/<int:pk>/",
        GradingEventViewSet.as_view({"get": "retrieve"}),
        name="grading-event-detail",
    ),
]
