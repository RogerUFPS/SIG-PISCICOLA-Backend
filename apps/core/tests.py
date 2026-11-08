from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
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
            user=self.operator,
            description="Farm updated",
            type_source=AuditLog.TypeSource.FARM,
        )
        FarmRoleAppPermission.objects.create(
            role=self.role,
            module="alerts",
            can_view=True,
        )

        alerts_url = f"/api/farms/core/{self.farm.pk}/alerts/"
        logs_url = f"/api/farms/core/{self.farm.pk}/auditlogs/"
        self.assertEqual(self.client.get(alerts_url).status_code, 200)
        self.assertEqual(self.client.get(logs_url).status_code, 403)

        FarmRoleAppPermission.objects.create(
            role=self.role,
            module="audit_logs",
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
        results = response.data["results"]
        self.assertTrue(
            any(log["description"] == "Farm updated" for log in results)
        )
        self.assertTrue(all(log["farm_id"] == self.farm.pk for log in results))
        farm_change = next(
            log for log in results if log["description"] == "Farm updated"
        )
        self.assertEqual(farm_change["user"], self.operator.pk)
        self.assertEqual(farm_change["user_name"], "core-operator@example.com")

    def test_audit_response_includes_actor_name_and_email_fallback(self):
        self.operator.name = "Ana"
        self.operator.lastname = "Pérez"
        self.operator.save(update_fields=["name", "lastname"])
        audit_log = AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="Role changed",
            type_source=AuditLog.TypeSource.USER_FARM,
        )
        FarmRoleAppPermission.objects.create(
            role=self.role,
            module="audit_logs",
            can_view=True,
        )

        list_response = self.client.get(
            f"/api/farms/core/{self.farm.pk}/auditlogs/"
        )
        detail_response = self.client.get(
            f"/api/farms/core/{self.farm.pk}/auditlogs/{audit_log.pk}/"
        )

        self.assertEqual(list_response.status_code, 200)
        list_item = next(
            log
            for log in list_response.data["results"]
            if log["id"] == audit_log.pk
        )
        self.assertEqual(list_item["user"], self.operator.pk)
        self.assertEqual(list_item["user_name"], "Ana Pérez")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["user_name"], "Ana Pérez")

        self.operator.name = None
        self.operator.lastname = None
        self.operator.save(update_fields=["name", "lastname"])
        detail_response = self.client.get(
            f"/api/farms/core/{self.farm.pk}/auditlogs/{audit_log.pk}/"
        )
        self.assertEqual(
            detail_response.data["user_name"],
            self.operator.email,
        )

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
            module="alerts",
            can_view=True,
        )
        FarmRoleAppPermission.objects.create(
            role=self.role,
            module="audit_logs",
            can_view=True,
        )

        alert_url = f"/api/farms/core/{self.farm.pk}/alerts/{alert.pk}/"
        log_url = f"/api/farms/core/{self.farm.pk}/auditlogs/{audit_log.pk}/"
        logs_url = f"/api/farms/core/{self.farm.pk}/auditlogs/"
        self.assertIn(
            self.client.patch(
                alert_url, {"message": "Changed"}, format="json"
            ).status_code,
            (403, 405),
        )
        self.assertIn(self.client.delete(log_url).status_code, (403, 405))
        self.assertIn(
            self.client.post(
                logs_url,
                {
                    "description": "Injected log",
                    "type_source": AuditLog.TypeSource.FARM,
                },
                format="json",
            ).status_code,
            (403, 405),
        )
        with self.assertRaises(ValidationError):
            audit_log.description = "Changed"
            audit_log.save()
        with self.assertRaises(ValidationError):
            audit_log.delete()
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=audit_log.pk).update(
                description="Changed"
            )
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE audit_log SET description = %s WHERE id = %s",
                        ["Changed", audit_log.pk],
                    )
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM audit_log WHERE id = %s",
                        [audit_log.pk],
                    )

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

    def test_farm_owned_changes_are_audited(self):
        role = FarmRole.objects.create(farm=self.farm, name="Audited role")
        created = AuditLog.objects.get(
            farm_id=self.farm.pk,
            type_source=AuditLog.TypeSource.FARM_ROLE,
            source_id=role.pk,
            description=f"FarmRole {role.pk} created",
        )
        self.assertIsNone(created.old_values)
        self.assertEqual(created.new_values["name"], "Audited role")

        role.name = "Renamed role"
        role.save()
        updated = AuditLog.objects.get(
            farm_id=self.farm.pk,
            type_source=AuditLog.TypeSource.FARM_ROLE,
            source_id=role.pk,
            description=f"FarmRole {role.pk} updated",
        )
        self.assertEqual(updated.old_values["name"], "Audited role")
        self.assertEqual(updated.new_values["name"], "Renamed role")

        role_id = role.pk
        role.delete()
        deleted = AuditLog.objects.get(
            farm_id=self.farm.pk,
            type_source=AuditLog.TypeSource.FARM_ROLE,
            source_id=role_id,
            description=f"FarmRole {role_id} deleted",
        )
        self.assertEqual(deleted.old_values["name"], "Renamed role")
        self.assertIsNone(deleted.new_values)

    def test_audit_logs_are_always_paginated(self):
        FarmRoleAppPermission.objects.create(
            role=self.role,
            module="audit_logs",
            can_view=True,
        )
        AuditLog.objects.bulk_create(
            [
                AuditLog(
                    farm_id=self.farm.pk,
                    description=f"Page test {index}",
                    type_source=AuditLog.TypeSource.FARM,
                )
                for index in range(55)
            ]
        )
        expected_count = AuditLog.objects.filter(farm_id=self.farm.pk).count()

        url = f"/api/farms/core/{self.farm.pk}/auditlogs/"
        first_page = self.client.get(url)
        second_page = self.client.get(url, {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.data["count"], expected_count)
        self.assertEqual(len(first_page.data["results"]), 50)
        self.assertIsNotNone(first_page.data["next"])
        self.assertEqual(len(second_page.data["results"]), expected_count - 50)
        self.assertIsNone(second_page.data["next"])

    @patch("apps.core.utils.ensure_overdue_events_alerts")
    def test_unrelated_role_grant_does_not_grant_core_read_permissions(
        self, _ensure_alerts
    ):
        FarmRoleAppPermission.objects.create(
            role=self.role,
            module="farm_management",
            can_view=True,
        )
        alerts_url = f"/api/farms/core/{self.farm.pk}/alerts/"
        logs_url = f"/api/farms/core/{self.farm.pk}/auditlogs/"

        self.assertEqual(self.client.get(alerts_url).status_code, 403)
        self.assertEqual(self.client.get(logs_url).status_code, 403)
