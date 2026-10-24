from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.accounts.views import get_tokens_for_user
from apps.farms.models import (
    City,
    Department,
    Farm,
    FarmRole,
    FarmRoleAppPermission,
    UserFarm,
)

from .models import Alert, AuditLog, Unit


class CoreAccessTests(TestCase):
    def setUp(self):
        operator_role = Role.objects.create(name="Operario")
        self.operator = User.objects.create_user(
            email="core-operator@example.com",
            password="test-password-123",
            role=operator_role,
            is_profile_complete=True,
        )
        department = Department.objects.create(name="Core test department")
        city = City.objects.create(name="Core test city", department=department)
        self.farm = Farm.objects.create(
            name="Core test farm",
            department=department,
            city=city,
            address="Test",
            total_area_ha=1,
        )
        role = FarmRole.objects.create(
            farm=self.farm,
            name="Core reader",
            permissions_configured=True,
        )
        UserFarm.objects.create(user=self.operator, farm=self.farm, farm_role=role)
        self.role = role
        tokens = get_tokens_for_user(self.operator)
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {tokens['access']}"
        )

    @patch("apps.core.utils.ensure_overdue_events_alerts")
    def test_alerts_and_audit_logs_have_independent_view_grants(self, _ensure_alerts):
        Alert.objects.create(
            farm=self.farm,
            source_type=Alert.SourceType.HEALTH,
            description="Health alert",
            message="Review",
        )
        AuditLog.objects.create(
            farm_id=self.farm.pk,
            description="Farm updated",
            type_source=AuditLog.TypeSource.FARM,
        )
        FarmRoleAppPermission.objects.create(
            role=self.role,
            app="core_alerts",
            can_view=True,
        )

        alerts_url = f"/api/farms/core/{self.farm.pk}/alerts/"
        logs_url = f"/api/farms/core/{self.farm.pk}/auditlogs/"
        self.assertEqual(self.client.get(alerts_url).status_code, 200)
        self.assertEqual(self.client.get(logs_url).status_code, 403)

        FarmRoleAppPermission.objects.create(
            role=self.role,
            app="core_auditlogs",
            can_view=True,
        )
        other_farm = Farm.objects.create(
            name="Other core farm",
            department=self.farm.department,
            city=self.farm.city,
            address="Other",
            total_area_ha=1,
        )
        AuditLog.objects.create(
            farm_id=other_farm.pk,
            description="Other farm updated",
            type_source=AuditLog.TypeSource.FARM,
        )
        response = self.client.get(logs_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    @patch("apps.core.utils.ensure_overdue_events_alerts")
    def test_alerts_and_audit_logs_are_read_only(self, _ensure_alerts):
        alert = Alert.objects.create(
            farm=self.farm,
            source_type=Alert.SourceType.HEALTH,
            description="Health alert",
            message="Review",
        )
        audit_log = AuditLog.objects.create(
            farm_id=self.farm.pk,
            description="Farm updated",
            type_source=AuditLog.TypeSource.FARM,
        )
        FarmRoleAppPermission.objects.create(
            role=self.role,
            app="core_alerts",
            can_view=True,
        )
        FarmRoleAppPermission.objects.create(
            role=self.role,
            app="core_auditlogs",
            can_view=True,
        )

        alert_url = f"/api/farms/core/{self.farm.pk}/alerts/{alert.pk}/"
        log_url = f"/api/farms/core/{self.farm.pk}/auditlogs/{audit_log.pk}/"
        self.assertIn(
            self.client.patch(
                alert_url, {"message": "Changed"}, format="json"
            ).status_code,
            (403, 405),
        )
        self.assertIn(self.client.delete(log_url).status_code, (403, 405))

    def test_units_are_publicly_readable_and_read_only(self):
        Unit.objects.create(symbol="kg", name="Kilogram")

        client = APIClient()
        self.assertEqual(client.get("/api/unit/").status_code, 200)
        self.assertEqual(
            client.post(
                "/api/unit/",
                {"symbol": "g", "name": "Gram"},
                format="json",
            ).status_code,
            405,
        )
