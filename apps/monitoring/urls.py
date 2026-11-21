from django.urls import path

from .views import ControlStatViewSet, DailyStatViewSet, FishEvaluatedViewSet

urlpatterns = [
    # Fish Evaluations
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/fish-evaluations/",
        FishEvaluatedViewSet.as_view(
            {
                "get": "list",
                "post": "create",
            }
        ),
        name="fish-evaluation-list",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/fish-evaluations/<int:pk>/",
        FishEvaluatedViewSet.as_view(
            {
                "get": "retrieve",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="fish-evaluation-detail",
    ),
    # Daily Stats
    path(
        "farms/<int:farm_pk>/daily-stats/",
        DailyStatViewSet.as_view(
            {
                "get": "list",
                "post": "create",
            }
        ),
        name="daily-stat-list",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/daily-stats/",
        DailyStatViewSet.as_view(
            {
                "get": "list",
                "post": "create",
            }
        ),
        name="daily-stat-cycle-list",
    ),
    path(
        "farms/<int:farm_pk>/daily-stats/<int:pk>/",
        DailyStatViewSet.as_view(
            {
                "get": "retrieve",
                "patch": "partial_update",
                "delete": "destroy",
            }
        ),
        name="daily-stat-detail",
    ),
    # Control Stats (READ-ONLY - generados automáticamente desde FishEvaluated)
    path(
        "farms/<int:farm_pk>/control-stats/",
        ControlStatViewSet.as_view(
            {
                "get": "list",
            }
        ),
        name="control-stat-list",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/control-stats/",
        ControlStatViewSet.as_view(
            {
                "get": "list",
            }
        ),
        name="control-stat-cycle-list",
    ),
    path(
        "farms/<int:farm_pk>/control-stats/<int:pk>/",
        ControlStatViewSet.as_view(
            {
                "get": "retrieve",
            }
        ),
        name="control-stat-detail",
    ),
]
