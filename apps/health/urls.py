from django.urls import path

from .views import (CycleHealthStatDetailView, CycleHealthStatListCreateView,
                    CycleHealthStatWithFishEvaluationCreateView,
                    CycleTreatmentEventListView, HealthOptionsView,
                    HealthStatTreatmentPlanDetailView,
                    HealthStatTreatmentPlanEventDetailView,
                    HealthStatTreatmentPlanEventListView,
                    HealthStatTreatmentPlanListCreateView,
                    TreatmentPlanOccupiedRangesView)

urlpatterns = [
    path(
        "health/options/",
        HealthOptionsView.as_view(),
        name="health-options",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/health-stats/",
        CycleHealthStatListCreateView.as_view(),
        name="health-stat-list",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/health-stats/with-fish-evaluation/",
        CycleHealthStatWithFishEvaluationCreateView.as_view(),
        name="health-stat-with-fish-evaluation",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/health-stats/<int:health_stat_id>/",
        CycleHealthStatDetailView.as_view(),
        name="health-stat-detail",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/health-stats/<int:health_stat_id>/treatment-plans/occupied-ranges/",
        TreatmentPlanOccupiedRangesView.as_view(),
        name="treatment-plan-occupied-ranges",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/health-stats/<int:health_stat_id>/treatment-plans/",
        HealthStatTreatmentPlanListCreateView.as_view(),
        name="treatment-plan-list",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/treatment-events/",
        CycleTreatmentEventListView.as_view(),
        name="cycle-treatment-event-list",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/health-stats/<int:health_stat_id>/treatment-plans/<int:plan_id>/",
        HealthStatTreatmentPlanDetailView.as_view(),
        name="treatment-plan-detail",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/health-stats/<int:health_stat_id>/treatment-plans/<int:plan_id>/treatment-events/",
        HealthStatTreatmentPlanEventListView.as_view(),
        name="treatment-event-list",
    ),
    path(
        "farms/<int:farm_pk>/ponds/<int:pond_pk>/cycles/<int:cycle_pk>/health-stats/<int:health_stat_id>/treatment-plans/<int:plan_id>/treatment-events/<int:event_id>/",
        HealthStatTreatmentPlanEventDetailView.as_view(),
        name="treatment-event-detail",
    ),
]
