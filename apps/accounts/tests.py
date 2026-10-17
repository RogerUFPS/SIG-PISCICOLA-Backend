from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import SessionJWTAuthentication
from .models import Role, RoleAppPermission, User, UserSession
from .permissions import AppPermission
from .views import get_tokens_for_user


class SpeciesView:
    __module__ = "apps.species.views"


class AccountAuthenticationTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(name="Operario")
        self.user = User.objects.create_user(
            email="operario@example.com",
            password="secure-password",
            role=self.role,
            is_profile_complete=True,
        )
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
        RoleAppPermission.objects.create(
            role=self.role,
            app="species",
            can_view=True,
            can_create=False,
            can_edit=True,
            can_delete=False,
        )
        request = APIRequestFactory().get("/api/species/")
        request.user = self.user

        self.assertTrue(AppPermission().has_permission(request, SpeciesView()))

        request.method = "POST"
        self.assertFalse(AppPermission().has_permission(request, SpeciesView()))

        RoleAppPermission.objects.filter(role=self.role, app="species").update(
            can_create=True
        )
        self.assertTrue(AppPermission().has_permission(request, SpeciesView()))

    def test_admin_can_create_roles_with_app_permissions(self):
        admin_role = Role.objects.create(name="Admin")
        admin = User.objects.create_user(
            email="admin@example.com",
            password="secure-password",
            role=admin_role,
            is_profile_complete=True,
        )
        tokens = get_tokens_for_user(admin)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        apps_response = client.get("/api/roles/apps/")
        self.assertEqual(apps_response.status_code, 200)
        self.assertIn("species", {item["app"] for item in apps_response.data})

        response = client.post(
            "/api/roles/",
            {
                "name": "Gestor",
                "app_permissions": [
                    {
                        "app": "species",
                        "can_view": True,
                        "can_create": False,
                        "can_edit": True,
                        "can_delete": False,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        permission = RoleAppPermission.objects.get(
            role__name="Gestor",
            app="species",
        )
        self.assertTrue(permission.can_view)
        self.assertTrue(permission.can_edit)

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
