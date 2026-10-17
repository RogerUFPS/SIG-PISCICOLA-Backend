# views.py

from django.apps import apps
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db.models import ProtectedError
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import SessionTokenRefreshSerializer
from .models import Invitation, Role, User, UserSession
from .permissions import AdminOr, IsAdmin, IsAdminOrValid, IsProductor
from .serializers import (ChangePasswordSerializer, CompleteProfileSerializer,
                          ConfirmResetPasswordSerializer, InvitationSerializer,
                          InviteOperarioSerializer, InviteProductorSerializer,
                          LoginSerializer, OperarioSerializer, RoleSerializer,
                          ResetPasswordSerializer, UserProfileSerializer,
                          get_role_permission_app_labels)
from .utils import (accept_invitation, change_user_password, invite_operario,
                    invite_productor, send_reset_password_email)


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    session = UserSession.objects.create(
        user=user,
        expires_at=timezone.now() + settings.JWT_SESSION_ABSOLUTE_LIFETIME,
    )
    refresh["sid"] = str(session.pk)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def get_pending_invitation(invitation_id, user):
    return Invitation.objects.filter(
        pk=invitation_id,
        user=user,
        status=Invitation.Status.PENDING,
    ).first()


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Contraseña actualizada correctamente."},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response(
            {
                "tokens": get_tokens_for_user(user),
                "is_profile_complete": user.is_profile_complete,
            },
            status=status.HTTP_200_OK,
        )


class SessionTokenRefreshView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = SessionTokenRefreshSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh_value = (
            request.data.get("refresh") if isinstance(request.data, dict) else None
        )
        if not isinstance(refresh_value, str) or not refresh_value:
            return Response(
                {"detail": "Debes enviar el token de renovación."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_value)
        except TokenError:
            return Response(
                {"detail": "El token de renovación es inválido o ya venció."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_id = token.get("sid")
        if session_id:
            session = UserSession.objects.filter(
                pk=session_id,
                user_id=token.get("user_id"),
                revoked_at__isnull=True,
            ).first()
            if session:
                session.revoked_at = timezone.now()
                session.save(update_fields=["revoked_at"])
        token.blacklist()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompleteProfileView(APIView):
    permission_classes = [IsAdminOrValid]

    def post(self, request):
        if request.user.is_profile_complete:
            return Response(
                {"detail": "El perfil ya está completo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = CompleteProfileSerializer(
            request.user, data=request.data, context={"request": request}
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Perfil completado correctamente."},
            status=status.HTTP_200_OK,
        )


class InviteProductorView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        serializer = InviteProductorSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        invite_productor(
            email=serializer.validated_data["email"],
            creator=request.user,
        )
        return Response(
            {"detail": "Invitación enviada al Productor."},
            status=status.HTTP_201_CREATED,
        )


class InviteOperarioView(APIView):
    permission_classes = [AdminOr(IsProductor)]

    def post(self, request):
        serializer = InviteOperarioSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            invite_operario(
                email=serializer.validated_data["email"],
                farm_id=serializer.validated_data["farm_id"],
                creator=request.user,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"detail": "Invitación procesada correctamente."},
            status=status.HTTP_201_CREATED,
        )


class InvitationListView(generics.ListAPIView):
    serializer_class = InvitationSerializer
    permission_classes = [AdminOr(IsProductor)]

    def get_queryset(self):
        return Invitation.objects.filter(invited_by=self.request.user).select_related(
            "invited_by",
            "user",
            "farm_id",
        )


class InvitationDetailView(generics.RetrieveAPIView):
    serializer_class = InvitationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Invitation.objects.filter(user=self.request.user).select_related(
            "invited_by",
            "user",
            "farm_id",
        )


class AcceptInvitationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        invitation = get_pending_invitation(pk, request.user)
        if not invitation:
            return Response(
                {"detail": "Invitación no encontrada o ya procesada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        accept_invitation(invitation, request.user)
        return Response(
            {"detail": "Invitación aceptada."},
            status=status.HTTP_200_OK,
        )


class RejectInvitationView(APIView):
    permission_classes = [IsAdminOrValid]

    def post(self, request, pk):
        invitation = get_pending_invitation(pk, request.user)

        if not invitation:
            return Response(
                {"detail": "Invitación no encontrada o ya procesada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        invitation.status = Invitation.Status.REJECTED
        invitation.save(update_fields=["status"])
        return Response(
            {"detail": "Invitación rechazada."},
            status=status.HTTP_200_OK,
        )


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAdminOrValid]

    def get_object(self):
        return self.request.user


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.filter(email=email).first()

        if user:
            token_generator = PasswordResetTokenGenerator()
            uuidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            send_reset_password_email(user.email, uuidb64, token)

        return Response(
            {"message": "Si el correo existe en la plataforma, se envió el enlace."},
            status=status.HTTP_200_OK,
        )


class ConfirmResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, uuidb64, token):
        user = self._get_valid_user_from_token(uuidb64, token)
        if not user:
            return Response(
                {"error": "Token inválido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"message": "Token válido."}, status=status.HTTP_200_OK)

    def post(self, request, uuidb64, token):
        user = self._get_valid_user_from_token(uuidb64, token)
        if not user:
            return Response(
                {"error": "Token inválido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ConfirmResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        change_user_password(user, serializer.validated_data["new_password"])
        return Response(
            {"detail": "Contraseña restablecida correctamente."},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _get_user(uuidb64):
        try:
            uid = urlsafe_base64_decode(uuidb64).decode()
            return User.objects.get(pk=uid)
        except Exception:
            return None

    def _get_valid_user_from_token(self, uuidb64, token):
        user = self._get_user(uuidb64)
        if not user:
            return None
        return user if PasswordResetTokenGenerator().check_token(user, token) else None


class AdminListView(generics.ListAPIView):
    serializer_class = OperarioSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return User.objects.filter(role__name="Admin")


class ProductorListView(generics.ListAPIView):
    serializer_class = OperarioSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return User.objects.filter(role__name="Productor")


class ProductorOperarioListView(generics.ListAPIView):
    serializer_class = OperarioSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):

        UserFarm = apps.get_model("farms", "UserFarm")
        productor_id = self.kwargs["productor_id"]

        farm_ids = UserFarm.objects.filter(
            user_id=productor_id,
            is_owner=True,
        ).values_list("farm_id", flat=True)

        return User.objects.filter(
            user_farms__farm_id__in=farm_ids,
            role__name="Operario",
        ).distinct()


class RoleListCreateView(generics.ListCreateAPIView):
    serializer_class = RoleSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return Role.objects.prefetch_related("app_permissions").order_by("name")


class RoleAppListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        app_labels = get_role_permission_app_labels()
        return Response(
            [
                {"app": label, "name": label.replace("_", " ").title()}
                for label in sorted(app_labels)
            ]
        )


class RoleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoleSerializer
    permission_classes = [IsAdmin]
    queryset = Role.objects.prefetch_related("app_permissions")

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.users.exists():
            return Response(
                {"detail": "No se puede eliminar un rol que tiene usuarios asignados."},
                status=status.HTTP_409_CONFLICT,
            )
        try:
            role.delete()
        except ProtectedError:
            return Response(
                {"detail": "No se puede eliminar un rol que tiene usuarios asignados."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
