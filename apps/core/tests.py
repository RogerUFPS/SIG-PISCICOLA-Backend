from unittest.mock import patch
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.utils import timezone
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

    def grant_audit_read(self):
        FarmRoleAppPermission.objects.get_or_create(
            role=self.role,
            module="audit_logs",
            defaults={"can_view": True},
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

    def test_audit_logs_can_filter_by_date_origin_user_and_ip(self):
        self.grant_audit_read()
        matching = AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="Matching event",
            type_source=AuditLog.TypeSource.FARM_ROLE,
            source_id=12,
            ip="192.0.2.10",
        )
        AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="Other origin",
            type_source=AuditLog.TypeSource.FARM,
            source_id=12,
            ip="192.0.2.10",
        )
        AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="Other origin ID",
            type_source=AuditLog.TypeSource.FARM_ROLE,
            source_id=13,
            ip="192.0.2.10",
        )
        AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="Other IP",
            type_source=AuditLog.TypeSource.FARM_ROLE,
            source_id=12,
            ip="192.0.2.11",
        )
        url = f"/api/farms/core/{self.farm.pk}/auditlogs/"
        params = {
            "date_from": date.today().isoformat(),
            "date_to": date.today().isoformat(),
            "origin": "FarmRole",
            "origin_id": "12",
            "user": self.operator.email,
            "ip": "192.0.2.10",
        }

        response = self.client.get(url, params)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], matching.pk)

    def test_audit_log_user_filter_accepts_id_and_name(self):
        self.grant_audit_read()
        self.operator.name = "Ana"
        self.operator.lastname = "Pérez"
        self.operator.save(update_fields=["name", "lastname"])
        other_user = User.objects.create(
            email="another-user@example.com",
            role=self.operator.role,
            name="Carlos",
            lastname="Rojas",
            is_profile_complete=True,
        )
        audit_log = AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="User search event",
            type_source=AuditLog.TypeSource.FARM,
        )
        AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=other_user,
            description="Other user event",
            type_source=AuditLog.TypeSource.FARM,
        )
        url = f"/api/farms/core/{self.farm.pk}/auditlogs/"

        by_id = self.client.get(url, {"user": str(self.operator.pk)})
        by_name = self.client.get(url, {"user": "Ana Pérez"})
        by_email = self.client.get(url, {"user": self.operator.email})

        self.assertEqual(by_id.status_code, 200)
        self.assertEqual(by_name.status_code, 200)
        self.assertEqual(by_email.status_code, 200)
        other_log = AuditLog.objects.get(description="Other user event")
        for response in (by_id, by_name, by_email):
            result_ids = {item["id"] for item in response.data["results"]}
            self.assertIn(audit_log.pk, result_ids)
            self.assertNotIn(other_log.pk, result_ids)

    def test_audit_log_filters_work_independently(self):
        self.grant_audit_read()
        other_user = User.objects.create(
            email="other-filter-user@example.com",
            role=self.operator.role,
            name="Luis",
            lastname="Gómez",
            is_profile_complete=True,
        )
        today = timezone.localdate()
        old_timestamp = timezone.make_aware(
            datetime.combine(today - timedelta(days=2), time(hour=12))
        )

        def create_log(description, **kwargs):
            values = {
                "farm_id": self.farm.pk,
                "description": description,
                "type_source": AuditLog.TypeSource.FARM_ROLE,
                "source_id": 12,
                "ip": "192.0.2.10",
                "user": self.operator,
            }
            values.update(kwargs)
            return AuditLog.objects.create(**values)

        with patch("django.db.models.fields.timezone.now", return_value=old_timestamp):
            matching = create_log("Matching")

        end_of_day = timezone.make_aware(
            datetime.combine(
                today,
                time(hour=23, minute=59, second=59, microsecond=999999),
            )
        )
        other_origin = create_log(
            "Other origin",
            type_source=AuditLog.TypeSource.FARM,
        )
        other_origin_id = create_log("Other origin ID", source_id=13)
        other_ip = create_log("Other IP", ip="192.0.2.11")
        other_user = create_log("Other user", user=other_user)
        current_date = create_log("Current date")
        with patch("django.db.models.fields.timezone.now", return_value=end_of_day):
            late_today = create_log("Late today")
        start_of_day = timezone.make_aware(datetime.combine(today, time.min))
        with patch(
            "django.db.models.fields.timezone.now",
            return_value=start_of_day,
        ):
            early_today = create_log("Early today")
        ipv6 = create_log("IPv6", ip="2001:db8::1")
        fixture_ids = {
            matching.pk,
            other_origin.pk,
            other_origin_id.pk,
            other_ip.pk,
            other_user.pk,
            current_date.pk,
            late_today.pk,
            early_today.pk,
            ipv6.pk,
        }
        today_fixture_ids = fixture_ids - {matching.pk}

        url = f"/api/farms/core/{self.farm.pk}/auditlogs/"
        cases = [
            (
                {"origin": AuditLog.TypeSource.FARM_ROLE},
                today_fixture_ids - {other_origin.pk} | {matching.pk},
            ),
            (
                {"origin_id": "12"},
                today_fixture_ids - {other_origin_id.pk} | {matching.pk},
            ),
            (
                {"user": str(self.operator.pk)},
                today_fixture_ids - {other_user.pk} | {matching.pk},
            ),
            ({"user": "Luis Gómez"}, {other_user.pk}),
            (
                {"ip": "192.0.2.10"},
                today_fixture_ids - {other_ip.pk, ipv6.pk} | {matching.pk},
            ),
            ({"ip": "2001:0db8:0:0:0:0:0:1"}, {ipv6.pk}),
            ({"date_from": today.isoformat()}, today_fixture_ids),
            ({"date_to": today.isoformat()}, fixture_ids),
            (
                {"date_to": (today - timedelta(days=1)).isoformat()},
                {matching.pk},
            ),
        ]

        for params, expected_ids in cases:
            with self.subTest(params=params):
                response = self.client.get(url, params)
                self.assertEqual(response.status_code, 200, response.data)
                result_ids = {item["id"] for item in response.data["results"]}
                self.assertEqual(
                    result_ids & fixture_ids,
                    expected_ids,
                )

    def test_audit_log_combined_filters_intersect_and_keep_date_end_inclusive(self):
        self.grant_audit_read()
        today = timezone.localdate()
        matching = AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="Matching event",
            type_source=AuditLog.TypeSource.FARM_ROLE,
            source_id=12,
            ip="192.0.2.10",
        )
        AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="Other origin",
            type_source=AuditLog.TypeSource.FARM,
            source_id=12,
            ip="192.0.2.10",
        )

        response = self.client.get(
            f"/api/farms/core/{self.farm.pk}/auditlogs/",
            {
                "date_from": today.isoformat(),
                "date_to": today.isoformat(),
                "origin": "FarmRole",
                "origin_id": "12",
                "user": self.operator.email,
                "ip": "192.0.2.10",
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], matching.pk)

    def test_audit_log_empty_filter_values_are_ignored(self):
        self.grant_audit_read()
        AuditLog.objects.create(
            farm_id=self.farm.pk,
            user=self.operator,
            description="Unfiltered event",
            type_source=AuditLog.TypeSource.FARM,
        )
        url = f"/api/farms/core/{self.farm.pk}/auditlogs/"
        empty_filters = {
            "date_from": "",
            "date_to": "",
            "origin": "",
            "origin_id": "",
            "user": "",
            "ip": "",
        }

        unfiltered = self.client.get(url)
        with_empty_filters = self.client.get(url, empty_filters)

        self.assertEqual(unfiltered.status_code, 200)
        self.assertEqual(with_empty_filters.status_code, 200)
        self.assertEqual(with_empty_filters.data["count"], unfiltered.data["count"])
        self.assertEqual(
            {item["id"] for item in with_empty_filters.data["results"]},
            {item["id"] for item in unfiltered.data["results"]},
        )

    def test_audit_log_filter_validation_errors_return_400(self):
        self.grant_audit_read()
        url = f"/api/farms/core/{self.farm.pk}/auditlogs/"

        invalid_date = self.client.get(url, {"date_from": "07-11-2026"})
        invalid_order = self.client.get(
            url,
            {
                "date_from": (date.today() + timedelta(days=1)).isoformat(),
                "date_to": date.today().isoformat(),
            },
        )
        invalid_origin = self.client.get(url, {"origin": "NotAnAuditType"})
        invalid_origin_id = self.client.get(url, {"origin_id": "0"})
        invalid_origin_id_text = self.client.get(url, {"origin_id": "abc"})
        invalid_user = self.client.get(url, {"user": " "})
        invalid_ip = self.client.get(url, {"ip": "not-an-ip"})

        self.assertEqual(invalid_date.status_code, 400)
        self.assertEqual(invalid_order.status_code, 400)
        self.assertEqual(invalid_origin.status_code, 400)
        self.assertEqual(invalid_origin_id.status_code, 400)
        self.assertEqual(invalid_origin_id_text.status_code, 400)
        self.assertEqual(invalid_user.status_code, 400)
        self.assertEqual(invalid_ip.status_code, 400)

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
