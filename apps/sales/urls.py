# urls .py

from django.urls import path

from .views import (ClientCanDeleteView, ClientListCreateView,
                    ClientRetrieveUpdateDestroyView, FullSaleCreateView,
                    SaleCanEditView, SaleDetailCanEditView, SaleDetailEditView,
                    SaleDetailsBySaleView, SaleEditView, SaleListView,
                    SaleObservationsView, SaleRetrieveView, SalesByClientView,
                    SalesByHarvestClassificationView)

app_name = "sales"

urlpatterns = [
    path(
        "farms/<int:farm_pk>/clients/",
        ClientListCreateView.as_view(),
        name="client-list-create",
    ),
    path(
        "farms/<int:farm_pk>/clients/<int:pk>/",
        ClientRetrieveUpdateDestroyView.as_view(),
        name="client-detail",
    ),
    path(
        "farms/<int:farm_pk>/clients/<int:pk>/can-delete/",
        ClientCanDeleteView.as_view(),
        name="client-can-delete",
    ),
    path(
        "farms/<int:farm_pk>/sales/by-client/<int:client_id>/",
        SalesByClientView.as_view(),
        name="sales-by-client",
    ),
    path(
        "farms/<int:farm_pk>/sales/by-harvest-classification/<int:hc_id>/",
        SalesByHarvestClassificationView.as_view(),
        name="sales-by-harvest-classification",
    ),
    path(
        "farms/<int:farm_pk>/sales/",
        SaleListView.as_view(),
        name="sale-list",
    ),
    path(
        "farms/<int:farm_pk>/sales/create/",
        FullSaleCreateView.as_view(),
        name="sale-create",
    ),
    path(
        "farms/<int:farm_pk>/sales/<int:pk>/",
        SaleRetrieveView.as_view(),
        name="sale-detail",
    ),
    path(
        "farms/<int:farm_pk>/sales/<int:pk>/edit/",
        SaleEditView.as_view(),
        name="sale-edit",
    ),
    path(
        "farms/<int:farm_pk>/sales/<int:pk>/observations/",
        SaleObservationsView.as_view(),
        name="sale-observations",
    ),
    path(
        "farms/<int:farm_pk>/sales/<int:pk>/can-edit/",
        SaleCanEditView.as_view(),
        name="sale-can-edit",
    ),
    path(
        "farms/<int:farm_pk>/sale-details/by-sale/<int:sale_id>/",
        SaleDetailsBySaleView.as_view(),
        name="sale-details-by-sale",
    ),
    path(
        "farms/<int:farm_pk>/sale-details/<int:pk>/",
        SaleDetailEditView.as_view(),
        name="sale-detail-edit",
    ),
    path(
        "farms/<int:farm_pk>/sale-details/<int:pk>/can-edit/",
        SaleDetailCanEditView.as_view(),
        name="sale-detail-can-edit",
    ),
]
