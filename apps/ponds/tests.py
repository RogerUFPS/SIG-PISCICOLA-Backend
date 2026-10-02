from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.farms.utils import farm_has_active_resources
from apps.ponds.models import Pond
from apps.ponds.utils import pond_has_cycles, soft_delete_pond
from apps.ponds.views import PondInactivateView


class PondLifecycleProtectionTests(SimpleTestCase):
    def test_delete_is_blocked_when_pond_has_active_cycle(self):
        pond = Pond(status=Pond.Status.ACTIVE)
        active_cycle_query = MagicMock()
        active_cycle_query.exists.return_value = True

        with patch(
            "apps.cycle.models.Cycle.objects.filter",
            return_value=active_cycle_query,
        ), patch("apps.batch.models.PondBatch.objects.filter") as planting_filter:
            planting_filter.return_value.exists.return_value = False

            with self.assertRaisesMessage(
                ValueError,
                "No se puede eliminar el estanque porque tiene un ciclo o siembra activa.",
            ):
                soft_delete_pond(pond)

    def test_delete_is_blocked_when_pond_has_active_planting(self):
        pond = Pond(status=Pond.Status.ACTIVE)
        active_cycle_query = MagicMock()
        active_cycle_query.exists.return_value = False
        active_planting_query = MagicMock()
        active_planting_query.exists.return_value = True

        with patch(
            "apps.cycle.models.Cycle.objects.filter",
            return_value=active_cycle_query,
        ), patch(
            "apps.batch.models.PondBatch.objects.filter",
            return_value=active_planting_query,
        ):
            with self.assertRaises(ValueError):
                soft_delete_pond(pond)

    def test_inactivation_rule_detects_any_non_deleted_cycle(self):
        pond = Pond()
        cycle_query = MagicMock()
        cycle_query.exists.return_value = True

        with patch(
            "apps.cycle.models.Cycle.objects.filter",
            return_value=cycle_query,
        ) as cycle_filter:
            self.assertTrue(pond_has_cycles(pond))

        cycle_filter.assert_called_once_with(pond=pond, deleted_at__isnull=True)

    def test_inactivation_endpoint_rejects_pond_with_cycles(self):
        pond = Pond(status=Pond.Status.ACTIVE)
        request = object()

        with patch("apps.ponds.views._get_farm", return_value=object()), patch(
            "apps.ponds.views.get_pond_or_404", return_value=pond
        ), patch("apps.ponds.views.pond_has_cycles", return_value=True):
            response = PondInactivateView().patch(request, 1, 2)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(pond.status, Pond.Status.ACTIVE)

    def test_farm_active_resources_include_active_ponds_and_cycles(self):
        cycle_query = MagicMock()
        pond_query = MagicMock()
        cycle_query.exists.return_value = False
        pond_query.exclude.return_value.exists.return_value = True

        with patch(
            "apps.cycle.models.Cycle.objects.filter",
            return_value=cycle_query,
        ), patch(
            "apps.ponds.models.Pond.objects.filter",
            return_value=pond_query,
        ):
            self.assertTrue(farm_has_active_resources(object()))
