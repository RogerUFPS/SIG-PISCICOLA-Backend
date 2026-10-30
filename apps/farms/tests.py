from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.views import get_tokens_for_user

from .enums import FarmPermission
from .models import City, Department, Farm, FarmRole, FarmRoleAppPermission, UserFarm


class FarmRolePermissionsTests(TestCase):
    def setUp(self):
        self.producer_role = Role.objects.create(name="Productor")
        self.operator_role = Role.objects.create(name="Operario")
        self.producer = User.objects.create_user(
            email="producer@example.com",
            password="secure-password",
            role=self.producer_role,
            is_profile_complete=True,
        )
        self.operator = User.objects.create_user(
            email="operator@example.com",
            password="secure-password",
            role=self.operator_role,
            is_profile_complete=True,
        )
        department = Department.objects.create(name="Test Department")
        city = City.objects.create(name="Test City", department=department)
        self.farm = Farm.objects.create(
            name="Test Farm",
            department=department,
            city=city,
            address="Test",
            total_area_ha=1,
        )
        UserFarm.objects.create(
            user=self.producer,
            farm=self.farm,
            is_owner=True,
        )
        UserFarm.objects.create(user=self.operator, farm=self.farm)
        tokens = get_tokens_for_user(self.producer)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_producer_creates_farm_role_with_live_app_catalog(self):
        apps_response = self.client.get(
            f"/api/farms/{self.farm.pk}/roles/apps/"
        )
        self.assertEqual(apps_response.status_code, 200)
        app_labels = {item["app"] for item in apps_response.data}
        self.assertIn("species", app_labels)
        self.assertNotIn("accounts", app_labels)
        self.assertIn("core_alerts", app_labels)
        self.assertIn("core_auditlogs", app_labels)

        response = self.client.post(
            f"/api/farms/{self.farm.pk}/roles/",
            {
                "name": "Encargado sanitario",
                "app_permissions": [
                    {
                        "app": "health",
                        "can_view": True,
                        "can_create": True,
                        "can_edit": True,
                        "can_delete": False,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        role = FarmRole.objects.get(pk=response.data["id"], farm=self.farm)
        grant = FarmRoleAppPermission.objects.get(role=role, app="health")
        self.assertTrue(grant.can_view)
        self.assertTrue(grant.can_create)
        self.assertTrue(grant.can_edit)
        self.assertFalse(grant.can_delete)

    def test_core_permissions_cannot_be_configured_for_writes(self):
        response = self.client.post(
            f"/api/farms/{self.farm.pk}/roles/",
            {
                "name": "Core editor",
                "app_permissions": [
                    {
                        "app": "core_alerts",
                        "can_view": True,
                        "can_edit": True,
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_producer_assigns_role_to_operator_in_same_farm(self):
        role = FarmRole.objects.create(farm=self.farm, name="Inventario")
        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}/",
            {"farm_role": role.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        self.assertEqual(membership.farm_role_id, role.pk)

    def test_member_identity_cannot_be_changed(self):
        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}/",
            {"user_id": self.producer.pk, "status": "inactive"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        membership = UserFarm.objects.get(farm=self.farm, user=self.operator)
        self.assertEqual(membership.status, UserFarm.Status.INACTIVE)
        self.assertEqual(
            UserFarm.objects.filter(farm=self.farm, user=self.producer).count(),
            1,
        )

    def test_global_productor_role_does_not_grant_farm_permissions(self):
        non_owner = User.objects.create_user(
            email="non-owner@example.com",
            password="test-password-123",
            role=self.producer_role,
            is_profile_complete=True,
        )
        UserFarm.objects.create(user=non_owner, farm=self.farm)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(non_owner)['access']}"
        )

        response = self.client.get(f"/api/farms/{self.farm.pk}/roles/apps/")
        self.assertEqual(response.status_code, 403)

        UserFarm.objects.filter(user=non_owner, farm=self.farm).update(
            permissions=int(FarmPermission.MANAGE_USERS)
        )
        response = self.client.get(f"/api/farms/{self.farm.pk}/roles/apps/")
        self.assertEqual(response.status_code, 200)

    def test_existing_role_permissions_authorize_without_membership_copy(self):
        role = FarmRole.objects.create(
            farm=self.farm,
            name="Legacy permissions",
            permissions=int(
                FarmPermission.MANAGE_REVIEWS | FarmPermission.MANAGE_CYCLE
            ),
            permissions_configured=False,
        )
        UserFarm.objects.filter(user=self.operator, farm=self.farm).update(
            farm_role=role,
            permissions=0,
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(self.operator)['access']}"
        )

        self.assertEqual(
            self.client.get(f"/api/farms/{self.farm.pk}/daily-stats/").status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/api/farms/{self.farm.pk}/production-plans/"
            ).status_code,
            200,
        )

    def test_user_management_permission_is_read_from_existing_role(self):
        role = FarmRole.objects.create(
            farm=self.farm,
            name="Legacy user manager",
            permissions=int(FarmPermission.MANAGE_USERS),
        )
        UserFarm.objects.filter(user=self.operator, farm=self.farm).update(
            farm_role=role,
            permissions=0,
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(self.operator)['access']}"
        )

        self.assertEqual(
            self.client.get(f"/api/farms/{self.farm.pk}/members/").status_code,
            200,
        )

    def test_user_manager_cannot_grant_permissions_or_manage_owner(self):
        manager_membership = UserFarm.objects.get(
            user=self.operator,
            farm=self.farm,
        )
        manager_membership.permissions = int(FarmPermission.MANAGE_USERS)
        manager_membership.save(update_fields=["permissions"])
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(self.operator)['access']}"
        )

        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}/",
            {"permissions": ["MANAGE_FARM"]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/members/{self.producer.pk}/",
            {"status": "inactive"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.accounts.utils.send_email")
    def test_user_manager_can_invite_only_for_their_farm(self, send_email):
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.permissions = int(FarmPermission.MANAGE_USERS)
        membership.save(update_fields=["permissions"])
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(self.operator)['access']}"
        )

        response = self.client.post(
            "/api/invitations/operario/",
            {"email": "new-operator@example.com", "farm_id": self.farm.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        invited_user = User.objects.get(email="new-operator@example.com")
        invited_membership = UserFarm.objects.get(
            user=invited_user,
            farm=self.farm,
        )
        self.assertEqual(invited_membership.permissions, 0)
        self.assertIsNone(invited_membership.farm_role_id)
        send_email.assert_called_once()

        other_farm = Farm.objects.create(
            name="Other Test Farm",
            department=self.farm.department,
            city=self.farm.city,
            address="Other",
            total_area_ha=1,
        )
        response = self.client.post(
            "/api/invitations/operario/",
            {"email": "wrong-farm@example.com", "farm_id": other_farm.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email="wrong-farm@example.com").exists())

    def test_only_owner_can_edit_farm_roles(self):
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.permissions = int(FarmPermission.MANAGE_USERS)
        membership.save(update_fields=["permissions"])
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(self.operator)['access']}"
        )

        response = self.client.post(
            f"/api/farms/{self.farm.pk}/roles/",
            {"name": "No autorizado"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_role_permission_changes_revoke_member_access(self):
        role = FarmRole.objects.create(
            farm=self.farm,
            name="User manager",
            permissions=int(FarmPermission.MANAGE_USERS),
            permissions_configured=True,
        )
        self.client.patch(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}/",
            {"farm_role": role.pk},
            format="json",
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(self.operator)['access']}"
        )
        self.assertEqual(
            self.client.get(f"/api/farms/{self.farm.pk}/roles/apps/").status_code,
            200,
        )

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(self.producer)['access']}"
        )
        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/roles/{role.pk}/",
            {"permissions": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {get_tokens_for_user(self.operator)['access']}"
        )
        self.assertEqual(
            self.client.get(f"/api/farms/{self.farm.pk}/roles/apps/").status_code,
            403,
        )
