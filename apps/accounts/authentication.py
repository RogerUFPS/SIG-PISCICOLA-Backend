import uuid

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserSession


class SessionJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        try:
            session_id = uuid.UUID(str(token.get("sid")))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AuthenticationFailed("El token no pertenece a una sesión válida.") from exc
        now = timezone.now()
        session = UserSession.objects.filter(
            pk=session_id,
            user=user,
            revoked_at__isnull=True,
            expires_at__gt=now,
        ).first()
        if session is None:
            raise AuthenticationFailed("La sesión es inválida o ha vencido.")

        if now - session.last_activity >= settings.JWT_IDLE_TIMEOUT:
            UserSession.objects.filter(pk=session.pk).update(revoked_at=now)
            raise AuthenticationFailed("La sesión venció por inactividad.")

        session.last_activity = now
        session.save(update_fields=["last_activity"])
        return user, token


class SessionTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
        except TokenError as exc:
            raise serializers.ValidationError(
                {"refresh": "El token de renovación es inválido o ha vencido."}
            ) from exc

        try:
            session_id = uuid.UUID(str(refresh.get("sid")))
            user_id = int(refresh.get("user_id"))
        except (TypeError, ValueError, AttributeError) as exc:
            raise serializers.ValidationError(
                {"refresh": "El token no pertenece a una sesión válida."}
            ) from exc
        now = timezone.now()
        try:
            session = UserSession.objects.get(
                pk=session_id,
                user_id=user_id,
                revoked_at__isnull=True,
            )
        except UserSession.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"refresh": "La sesión es inválida o ha vencido."}
            ) from exc

        if session.expires_at <= now:
            raise serializers.ValidationError(
                {"refresh": "La sesión alcanzó su duración máxima."}
            )
        if now - session.last_activity >= settings.JWT_IDLE_TIMEOUT:
            session.revoked_at = now
            session.save(update_fields=["revoked_at"])
            raise serializers.ValidationError(
                {"refresh": "La sesión venció por inactividad."}
            )

        session.last_activity = now
        session.save(update_fields=["last_activity"])
        return super().validate(attrs)
