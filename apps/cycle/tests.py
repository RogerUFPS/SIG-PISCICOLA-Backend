from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import serializers

from apps.cycle.models import Cycle
from apps.cycle.serializers import CycleSerializer


class ActiveCycleValidationTests(SimpleTestCase):
    def test_rejects_second_in_progress_cycle_when_paused_cycle_exists(self):
        self._assert_second_active_cycle_rejected(Cycle.State.IN_PROGRESS)

    def test_rejects_paused_cycle_when_in_progress_cycle_exists(self):
        self._assert_second_active_cycle_rejected(Cycle.State.PAUSED)

    def _assert_second_active_cycle_rejected(self, requested_state):
        farm = MagicMock(id=10)
        active_cycles = MagicMock()
        active_cycles.exclude.return_value.exists.return_value = True

        with patch(
            "apps.cycle.serializers.Cycle.objects.filter",
            return_value=active_cycles,
        ) as cycle_filter:
            with self.assertRaises(serializers.ValidationError):
                CycleSerializer().validate(
                    {"farm": farm, "state": requested_state}
                )

        cycle_filter.assert_called_once_with(
            farm=farm,
            state__in=[Cycle.State.IN_PROGRESS, Cycle.State.PAUSED],
            deleted_at__isnull=True,
        )
