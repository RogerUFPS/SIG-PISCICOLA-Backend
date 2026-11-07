from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.models import Role, User
from apps.accounts.permissions import AppPermission
from apps.accounts.views import get_tokens_for_user
from apps.core.models import AuditLog

from .models import (
    City,
    Department,
    Farm,
    FarmRole,
    FarmRoleAppPermission,
    UserFarm,
    UserFarmPermission,
)
from .modules import APP_TO_MODULE, OPERATIONS
from .utils import get_effective_permissions


class FarmRolePermissionsTests(TestCase):
    def setUp(self):
        self.producer_role = Role.objects.create(name="Productor")
        self.operator_role = Role.objects.create(name="Operario")
        self.producer = User.objects.create_user(
            email="producer@example.com",
            password="test-password",
            role=self.producer_role,
            is_profile_complete=True,
        )
        self.operator = User.objects.create_user(
            email="operator@example.com",
            password="test-password",
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
        UserFarm.objects.create(user=self.producer, farm=self.farm, is_owner=True)
        UserFarm.objects.create(user=self.operator, farm=self.farm)
        self.producer_tokens = get_tokens_for_user(self.producer)
        self.operator_tokens = get_tokens_for_user(self.operator)
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.producer_tokens['access']}"
        )

    def role_permission(self, role, module, **operations):
        return FarmRoleAppPermission.objects.create(
            role=role,
            module=module,
            **operations,
        )

    def request_permission(self, method, module="species"):
        factory = APIRequestFactory()
        request = getattr(factory, method.lower())(
            f"/api/{module}/",
            {},
            format="json",
        )
        request.user = self.operator
        view = type(
            "PermissionView",
            (),
            {
                "__module__": f"apps.{module}.views",
                "permission_app": module,
                "kwargs": {"farm_pk": self.farm.pk},
            },
        )()
        return AppPermission().has_permission(request, view)

    def test_module_catalog_uses_business_capability_names(self):
        response = self.client.get(f"/api/farms/{self.farm.pk}/roles/modules/")

        self.assertEqual(response.status_code, 200)
        modules = {item["module"] for item in response.data}
        self.assertIn("species_catalog", modules)
        self.assertIn("pond_management", modules)
        self.assertIn("user_administration", modules)
        self.assertNotIn("species", modules)
        self.assertNotIn("accounts", modules)

    def test_default_farm_roles_have_explicit_operation_grants(self):
        roles = {
            role.name: set(
                role.module_permissions.values_list("module", flat=True)
            )
            for role in FarmRole.objects.filter(farm=self.farm)
        }

        self.assertEqual(roles["Operario"], {"fish_health"})
        self.assertEqual(
            roles["Biólogo"],
            {
                "fish_health",
                "water_quality_monitoring",
                "production_batches",
                "production_cycles",
                "farm_events",
                "feeding_management",
                "harvest_management",
                "pond_management",
            },
        )
        self.assertEqual(roles["Administrador de Granja"], set(APP_TO_MODULE.values()))
        for role in FarmRole.objects.filter(farm=self.farm):
            for grant in role.module_permissions.all():
                self.assertTrue(grant.can_view)
                expected_write = grant.module not in ("alerts", "audit_logs")
                self.assertEqual(grant.can_create, expected_write)
                self.assertEqual(grant.can_update, expected_write)
                self.assertEqual(grant.can_delete, expected_write)

    def test_role_only_access_is_exactly_its_operations(self):
        role = FarmRole.objects.create(farm=self.farm, name="Health reviewer")
        self.role_permission(
            role,
            "fish_health",
            can_view=True,
            can_create=False,
            can_update=True,
            can_delete=False,
        )
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.farm_role = role
        membership.save(update_fields=["farm_role"])

        self.assertTrue(self.request_permission("get", module="health"))
        self.assertFalse(self.request_permission("post", module="health"))
        self.assertTrue(self.request_permission("patch", module="health"))
        self.assertFalse(self.request_permission("delete", module="health"))
        self.assertEqual(membership.personal_permissions.count(), 0)
        self.assertEqual(
            {
                (item["module"], item["operation"])
                for item in get_effective_permissions(membership)
            },
            {("fish_health", "view"), ("fish_health", "update")},
        )

    def test_personalized_operation_beyond_role_is_granted(self):
        role = FarmRole.objects.create(farm=self.farm, name="Species reader")
        self.role_permission(role, "species_catalog", can_view=True)
        UserFarm.objects.filter(user=self.operator, farm=self.farm).update(
            farm_role=role
        )

        response = self.client.post(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}/personal-permissions/",
            {"module": "species_catalog", "operation": "create"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.request_permission("post", module="species"))
        self.assertFalse(self.request_permission("patch", module="species"))

    def test_unrelated_personal_grant_never_revokes_role_grant(self):
        role = FarmRole.objects.create(farm=self.farm, name="Species viewer")
        self.role_permission(role, "species_catalog", can_view=True)
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.farm_role = role
        membership.save(update_fields=["farm_role"])

        response = self.client.post(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}/personal-permissions/",
            {"module": "inventory_products", "operation": "create"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.request_permission("get", module="species"))
        self.assertTrue(self.request_permission("post", module="products"))
        effective = UserFarm.objects.get(pk=membership.pk)
        self.assertEqual(
            set(
                effective.personal_permissions.values_list("module", "operation")
            ),
            {("inventory_products", "create")},
        )

    def test_missing_personal_grant_does_not_deny_role_operation(self):
        role = FarmRole.objects.create(farm=self.farm, name="Species viewer")
        self.role_permission(role, "species_catalog", can_view=True)
        UserFarm.objects.filter(user=self.operator, farm=self.farm).update(
            farm_role=role
        )

        self.assertFalse(
            UserFarmPermission.objects.filter(
                user_farm__user=self.operator,
                module="species_catalog",
            ).exists()
        )
        self.assertTrue(self.request_permission("get", module="species"))

    def test_every_module_checks_each_supported_role_operation(self):
        role = FarmRole.objects.create(farm=self.farm, name="Capability matrix")
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.farm_role = role
        membership.save(update_fields=["farm_role"])
        methods = {
            "view": ("get", "can_view"),
            "create": ("post", "can_create"),
            "update": ("patch", "can_update"),
            "delete": ("delete", "can_delete"),
        }

        for app, module in APP_TO_MODULE.items():
            grant = self.role_permission(
                role,
                module,
                can_view=False,
                can_create=False,
                can_update=False,
                can_delete=False,
            )
            supported = ("view",) if module in ("alerts", "audit_logs") else OPERATIONS
            for operation in supported:
                method, field = methods[operation]
                setattr(grant, field, True)
                grant.save(update_fields=[field])
                self.assertTrue(
                    self.request_permission(method, module=app),
                    f"{module}.{operation} must be granted by its role",
                )
                for other_operation, (other_method, _) in methods.items():
                    if other_operation != operation:
                        self.assertFalse(
                            self.request_permission(other_method, module=app),
                            f"{module}.{other_operation} must remain denied",
                        )
                setattr(grant, field, False)
                grant.save(update_fields=[field])

    def test_personalized_permission_requires_one_valid_operation(self):
        url = (
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}"
            "/personal-permissions/"
        )
        bundle = self.client.post(
            url,
            {
                "module": "species_catalog",
                "operation": "view",
                "operations": ["view", "update"],
            },
            format="json",
        )
        invalid = self.client.post(
            url,
            {"module": "species_catalog", "operation": "deny"},
            format="json",
        )

        self.assertEqual(bundle.status_code, 400)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(UserFarmPermission.objects.count(), 0)

    def test_member_patch_rejects_personal_permission_bundles(self):
        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}/",
            {
                "personal_permissions": [
                    {"module": "species_catalog", "operation": "view"},
                    {"module": "species_catalog", "operation": "update"},
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(UserFarmPermission.objects.count(), 0)

    def test_removing_personal_permission_keeps_role_permissions(self):
        role = FarmRole.objects.create(farm=self.farm, name="Species viewer")
        self.role_permission(role, "species_catalog", can_view=True)
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.farm_role = role
        membership.save(update_fields=["farm_role"])
        personal = UserFarmPermission.objects.create(
            user_farm=membership,
            module="species_catalog",
            operation="update",
        )

        response = self.client.delete(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}"
            f"/personal-permissions/{personal.pk}/"
        )

        self.assertEqual(response.status_code, 204)
        self.assertTrue(self.request_permission("get", module="species"))
        self.assertFalse(self.request_permission("patch", module="species"))

    def test_role_change_and_deactivation_leave_personal_grants_intact(self):
        role = FarmRole.objects.create(farm=self.farm, name="Temporary role")
        self.role_permission(role, "species_catalog", can_view=True)
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.farm_role = role
        membership.save(update_fields=["farm_role"])
        personal = UserFarmPermission.objects.create(
            user_farm=membership,
            module="inventory_products",
            operation="create",
        )

        response = self.client.delete(
            f"/api/farms/{self.farm.pk}/roles/{role.pk}/"
        )

        self.assertEqual(response.status_code, 204)
        membership.refresh_from_db()
        self.assertIsNone(membership.farm_role_id)
        self.assertTrue(UserFarmPermission.objects.filter(pk=personal.pk).exists())
        self.assertEqual(
            {
                (item["module"], item["operation"])
                for item in get_effective_permissions(membership)
            },
            {("inventory_products", "create")},
        )

    def test_redundant_personal_grant_is_harmless(self):
        role = FarmRole.objects.create(farm=self.farm, name="Species reader")
        self.role_permission(role, "species_catalog", can_view=True)
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.farm_role = role
        membership.save(update_fields=["farm_role"])
        url = (
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}"
            "/personal-permissions/"
        )

        created = self.client.post(
            url,
            {"module": "species_catalog", "operation": "view"},
            format="json",
        )
        duplicate = self.client.post(
            url,
            {"module": "species_catalog", "operation": "view"},
            format="json",
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(
            UserFarmPermission.objects.filter(
                user_farm=membership,
                module="species_catalog",
                operation="view",
            ).count(),
            1,
        )
        self.assertTrue(self.request_permission("get", module="species"))

    def test_changing_role_preserves_personal_permissions(self):
        personal = UserFarmPermission.objects.create(
            user_farm=UserFarm.objects.get(user=self.operator, farm=self.farm),
            module="inventory_products",
            operation="create",
        )
        role = FarmRole.objects.create(farm=self.farm, name="New role")
        self.role_permission(role, "species_catalog", can_view=True)

        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/members/{self.operator.pk}/",
            {"farm_role": role.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            UserFarmPermission.objects.filter(pk=personal.pk).exists()
        )
        effective = {
            (item["module"], item["operation"])
            for item in response.data["effective_permissions"]
        }
        self.assertEqual(
            effective,
            {
                ("inventory_products", "create"),
                ("species_catalog", "view"),
            },
        )

    def test_role_api_returns_operation_grants_and_audits_them(self):
        response = self.client.post(
            f"/api/farms/{self.farm.pk}/roles/",
            {
                "name": "Encargado sanitario",
                "module_permissions": [
                    {
                        "module": "fish_health",
                        "can_view": True,
                        "can_create": True,
                        "can_update": True,
                        "can_delete": False,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["module_permissions"][0]["module"], "fish_health")
        grant = FarmRoleAppPermission.objects.get(
            role_id=response.data["id"],
            module="fish_health",
        )
        self.assertTrue(grant.can_update)
        self.assertFalse(grant.can_delete)
        self.assertTrue(
            AuditLog.objects.filter(
                farm_id=self.farm.pk,
                source_id=grant.pk,
            ).exists()
        )

    def test_updating_role_replaces_only_role_grants(self):
        role = FarmRole.objects.create(farm=self.farm, name="Editable role")
        self.role_permission(role, "species_catalog", can_view=True)
        membership = UserFarm.objects.get(user=self.operator, farm=self.farm)
        membership.farm_role = role
        membership.save(update_fields=["farm_role"])
        personal = UserFarmPermission.objects.create(
            user_farm=membership,
            module="inventory_products",
            operation="create",
        )

        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/roles/{role.pk}/",
            {
                "module_permissions": [
                    {
                        "module": "fish_health",
                        "can_view": False,
                        "can_create": True,
                        "can_update": False,
                        "can_delete": False,
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["module_permissions"],
            [
                {
                    "module": "fish_health",
                    "can_view": False,
                    "can_create": True,
                    "can_update": False,
                    "can_delete": False,
                }
            ],
        )
        self.assertFalse(
            FarmRoleAppPermission.objects.filter(
                role=role,
                module="species_catalog",
            ).exists()
        )
        self.assertTrue(UserFarmPermission.objects.filter(pk=personal.pk).exists())
        membership.refresh_from_db()
        effective = {
            (item["module"], item["operation"])
            for item in get_effective_permissions(membership)
        }
        self.assertEqual(
            effective,
            {("fish_health", "create"), ("inventory_products", "create")},
        )

    def test_legacy_role_permission_bundle_is_not_accepted(self):
        response = self.client.post(
            f"/api/farms/{self.farm.pk}/roles/",
            {
                "name": "Invalid legacy role",
                "permissions": ["MANAGE_FARM"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            FarmRole.objects.filter(farm=self.farm, name="Invalid legacy role").exists()
        )
