from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.farms.models import (
    City,
    Department,
    Farm,
    FarmRole,
    FarmRoleAppPermission,
    UserFarm,
)

from .authentication import SessionJWTAuthentication
from .models import Role, User, UserSession
from .permissions import AppPermission
from .views import get_tokens_for_user


class SpeciesView:
    __module__ = "apps.species.views"

    def __init__(self, farm_id):
        self.kwargs = {"farm_pk": farm_id}


class AccountAuthenticationTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(name="Operario")
        self.user = User.objects.create_user(
            email="operario@example.com",
            password="secure-password",
            role=self.role,
            is_profile_complete=True,
        )
        department = Department.objects.create(name="Test Department")
        city = City.objects.create(name="Test City", department=department)
        farm = Farm.objects.create(
            name="Test Farm",
            department=department,
            city=city,
            address="Test",
            total_area_ha=1,
        )
        farm_role = FarmRole.objects.create(
            farm=farm,
            name="Consulta",
            permissions_configured=True,
        )
        UserFarm.objects.create(
            user=self.user,
            farm=farm,
            farm_role=farm_role,
            is_owner=False,
        )
        self.farm = farm
        self.farm_role = farm_role
        self.tokens = get_tokens_for_user(self.user)

    def test_authenticated_activity_extends_idle_timeout(self):
        session = UserSession.objects.get(user=self.user)
        session.last_activity = timezone.now() - timedelta(minutes=14)
        session.save(update_fields=["last_activity"])

        request = APIRequestFactory().get("/api/species/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.tokens['access']}"
        authenticated_user, _ = SessionJWTAuthentication().authenticate(request)

        self.assertEqual(authenticated_user, self.user)
        session.refresh_from_db()
        self.assertGreater(session.last_activity, timezone.now() - timedelta(minutes=1))

    def test_idle_session_is_rejected_and_revoked(self):
        session = UserSession.objects.get(user=self.user)
        session.last_activity = timezone.now() - timedelta(minutes=16)
        session.save(update_fields=["last_activity"])

        request = APIRequestFactory().get("/api/species/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {self.tokens['access']}"
        with self.assertRaises(AuthenticationFailed):
            SessionJWTAuthentication().authenticate(request)

        session.refresh_from_db()
        self.assertIsNotNone(session.revoked_at)

    def test_logout_revokes_access_and_refresh_tokens(self):
        client = APIClient()
        response = client.post(
            "/api/auth/logout/",
            {"refresh": self.tokens["refresh"]},
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        session = UserSession.objects.get(user=self.user)
        self.assertIsNotNone(session.revoked_at)
        with self.assertRaises(TokenError):
            RefreshToken(self.tokens["refresh"])

    def test_refresh_activity_extends_session_and_rotates_tokens(self):
        session = UserSession.objects.get(user=self.user)
        session.last_activity = timezone.now() - timedelta(minutes=14)
        session.save(update_fields=["last_activity"])

        response = APIClient().post(
            "/api/auth/token/refresh/",
            {"refresh": self.tokens["refresh"]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        session.refresh_from_db()
        self.assertGreater(session.last_activity, timezone.now() - timedelta(minutes=1))

    def test_role_app_permissions_apply_to_each_request(self):
        FarmRoleAppPermission.objects.create(
            role=self.farm_role,
            app="species",
            can_view=True,
            can_create=False,
            can_edit=True,
            can_delete=False,
        )
        request = APIRequestFactory().get("/api/species/")
        request.user = self.user

        view = SpeciesView(self.farm.pk)
        self.assertTrue(AppPermission().has_permission(request, view))

        request.method = "POST"
        self.assertFalse(AppPermission().has_permission(request, view))

        FarmRoleAppPermission.objects.filter(
            role=self.farm_role, app="species"
        ).update(
            can_create=True
        )
        self.assertTrue(AppPermission().has_permission(request, view))

    def test_permissions_from_one_farm_do_not_apply_to_another(self):
        department = self.farm.department
        city = self.farm.city
        other_farm = Farm.objects.create(
            name="Other Farm",
            department=department,
            city=city,
            address="Other",
            total_area_ha=1,
        )
        other_role = FarmRole.objects.create(
            farm=other_farm,
            name="Sin permisos de especies",
            permissions_configured=True,
        )
        UserFarm.objects.create(
            user=self.user,
            farm=other_farm,
            farm_role=other_role,
        )
        FarmRoleAppPermission.objects.create(
            role=self.farm_role,
            app="species",
            can_view=True,
        )
        request = APIRequestFactory().get("/api/species/")
        request.user = self.user

        self.assertFalse(
            AppPermission().has_permission(request, SpeciesView(other_farm.pk))
        )

    @override_settings(HOST_URL="https://sig-piscicola-frontend.vercel.app/")
    @patch("apps.accounts.utils.send_email")
    def test_password_reset_link_uses_frontend_domain(self, send_email):
        from .utils import send_reset_password_email

        send_reset_password_email("user@example.com", "uid", "token")

        html = send_email.call_args.args[2]
        self.assertIn(
            "https://sig-piscicola-frontend.vercel.app/resetPassword/?uid=uid&token=token",
            html,
        )
