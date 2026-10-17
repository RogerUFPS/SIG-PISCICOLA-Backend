# urls.py
from django.urls import path
from .views import (AcceptInvitationView, AdminListView, ChangePasswordView,
                    CompleteProfileView, ConfirmResetPasswordView,
                    InvitationDetailView, InvitationListView,
                    InviteOperarioView, InviteProductorView, LoginView,
                    LogoutView, ProductorListView, ProductorOperarioListView,
                    ProfileView, RejectInvitationView, ResetPasswordView,
                    SessionTokenRefreshView)

urlpatterns = [
    # Auth
    path("auth/login/", LoginView.as_view()),
    path("auth/logout/", LogoutView.as_view()),
    path("auth/token/refresh/", SessionTokenRefreshView.as_view()),
    path("auth/change-password/", ChangePasswordView.as_view()),
    path("auth/reset-password/", ResetPasswordView.as_view()),
    path(
        "auth/reset-password/<str:uuidb64>/<str:token>/",
        ConfirmResetPasswordView.as_view(),
    ),
    # Usuarios
    path("users/admin/", AdminListView.as_view()),
    path("users/productor/", ProductorListView.as_view()),
    path(
        "users/productor/<int:productor_id>/operarios/",
        ProductorOperarioListView.as_view(),
    ),
    path("users/me/", ProfileView.as_view()),
    path("users/me/complete/", CompleteProfileView.as_view()),
    # Invitaciones - envío
    path("invitations/productor/", InviteProductorView.as_view()),
    path("invitations/operario/", InviteOperarioView.as_view()),
    # Invitaciones - gestión
    path("invitations/", InvitationListView.as_view()),
    path("invitations/<int:pk>/", InvitationDetailView.as_view()),
    path("invitations/<int:pk>/accept/", AcceptInvitationView.as_view()),
    path("invitations/<int:pk>/reject/", RejectInvitationView.as_view()),
]
