# urls.py

from django.urls import path

from .views import (BatchFromClassificationView, HarvestClassificationListView,
                    HarvestDetailView, HarvestListCreateView)

urlpatterns = [
    path(
        "farms/<int:farm_pk>/harvests/",
        HarvestListCreateView.as_view(),
    ),
    path(
        "farms/<int:farm_pk>/harvests/<int:pk>/",
        HarvestDetailView.as_view(),
    ),
    path(
        "farms/<int:farm_pk>/harvests/<int:harvest_pk>/classifications/",
        HarvestClassificationListView.as_view(),
    ),
    path(
        "farms/<int:farm_pk>/harvests/<int:harvest_pk>/classifications/<int:classification_pk>/derive-batch/",
        BatchFromClassificationView.as_view(),
    ),
]
