from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.views import get_tokens_for_user

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
