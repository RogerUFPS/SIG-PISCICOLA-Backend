from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.models import Alert

from .signals import health_stat_disease_alert


class HealthStatAlertTests(SimpleTestCase):
    @patch("apps.health.signals.create_alert")
    def test_creates_farm_scoped_alert_for_new_disease(self, create_alert):
        instance = SimpleNamespace(
            id=17,
            farm=SimpleNamespace(name="Granja Uno"),
            pond=SimpleNamespace(name="Estanque A"),
            cycle=SimpleNamespace(name="Ciclo 2026"),
            disease_name="Ichthyophthirius",
            date=date(2026, 10, 19),
            severity_level=Alert.Severity.HIGH,
        )

        health_stat_disease_alert(
            sender=None,
            instance=instance,
            created=True,
        )

        create_alert.assert_called_once()
        kwargs = create_alert.call_args.kwargs
        self.assertEqual(kwargs["source_type"], Alert.SourceType.HEALTH_STAT)
        self.assertEqual(kwargs["source_id"], 17)
        self.assertEqual(kwargs["severity"], Alert.Severity.HIGH)

    @patch("apps.health.signals.create_alert")
    def test_does_not_duplicate_alert_when_disease_is_edited(self, create_alert):
        health_stat_disease_alert(
            sender=None,
            instance=SimpleNamespace(),
            created=False,
        )

        create_alert.assert_not_called()
