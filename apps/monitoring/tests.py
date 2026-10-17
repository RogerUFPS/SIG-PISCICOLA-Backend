from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase

from apps.cycle.models import Cycle
from apps.monitoring.serializers import FishEvaluatedSerializer
from apps.monitoring.views import FishEvaluatedViewSet
from apps.ponds.models import Pond


class FishEvaluatedValidationTests(SimpleTestCase):
    def setUp(self):
        self.cycle = MagicMock(
            state=Cycle.State.IN_PROGRESS,
            start_date=date(2026, 9, 29),
            finish_date=None,
        )
        self.pond = MagicMock(status=Pond.Status.IN_USE)
        self.context = {"cycle": self.cycle, "pond": self.pond}

    def _serializer(self, live_available=1000, **overrides):
        data = {
            "evaluation_date": "2026-10-01",
            "sampled_quantity": 30,
            "min_weight_g": 10,
            "max_weight_g": 20,
        }
        data.update(overrides)
        serializer = FishEvaluatedSerializer(data=data, context=self.context)
        active_batches = [MagicMock()]
        with patch.object(
            serializer, "_get_active_cycle_pond_batches", return_value=active_batches
        ), patch.object(
            serializer,
            "_get_available_live_quantity",
            return_value=live_available,
        ):
            serializer.is_valid()
        return serializer

    def test_rejects_sample_below_three_percent(self):
        serializer = self._serializer(sampled_quantity=29)

        self.assertIn("sampled_quantity", serializer.errors)
        self.assertIn("al menos el 3%", serializer.errors["sampled_quantity"][0])

    def test_accepts_sample_equal_to_three_percent(self):
        serializer = self._serializer(sampled_quantity=30)

        self.assertTrue(serializer.is_valid())

    def test_rounds_minimum_sample_up_to_a_whole_fish(self):
        serializer = self._serializer(sampled_quantity=10, live_available=334)

        self.assertIn("sampled_quantity", serializer.errors)
        self.assertIn("11 de 334", serializer.errors["sampled_quantity"][0])

        serializer = self._serializer(sampled_quantity=11, live_available=334)

        self.assertTrue(serializer.is_valid())

    def test_rejects_minimum_weight_above_maximum(self):
        serializer = self._serializer(min_weight_g=20, max_weight_g=10)

        self.assertIn("min_weight_g", serializer.errors)

    def test_rejects_evaluation_before_cycle_start(self):
        serializer = self._serializer(evaluation_date="2026-09-13")

        self.assertIn("evaluation_date", serializer.errors)

    def test_rejects_evaluation_after_cycle_finish(self):
        self.cycle.finish_date = date(2026, 10, 1)
        serializer = self._serializer(evaluation_date="2026-10-02")

        self.assertIn("evaluation_date", serializer.errors)


class FishEvaluationControlRefreshTests(TestCase):
    def test_refreshes_latest_evaluation_for_each_date_after_deletion(self):
        cycle = object()
        pond = object()
        first = MagicMock(evaluation_date=date(2026, 10, 1))
        latest_same_day = MagicMock(evaluation_date=date(2026, 10, 1))
        next_day = MagicMock(evaluation_date=date(2026, 10, 2))
        serializer = FishEvaluatedSerializer()

        with patch(
            "apps.monitoring.serializers.FishEvaluated.objects.filter"
        ) as filter_evaluations, patch.object(
            serializer, "_refresh_cycle_control_stat"
        ) as refresh, patch(
            "apps.monitoring.serializers.ControlStat.objects.filter"
        ) as control_stats:
            filter_evaluations.return_value.order_by.return_value = [
                first,
                latest_same_day,
                next_day,
            ]

            serializer._refresh_cycle_control_stats_from(
                cycle, pond, date(2026, 10, 1)
            )

        self.assertEqual(
            [call.args[0] for call in refresh.call_args_list],
            [latest_same_day, next_day],
        )
        self.assertTrue(
            all(call.kwargs == {"ignore_same_day": True} for call in refresh.call_args_list)
        )
        control_stats.return_value.exclude.assert_called_once()
        control_stats.return_value.exclude.return_value.update.assert_called_once()

    def test_delete_refreshes_derived_controls_from_deleted_evaluation_date(self):
        cycle = object()
        pond = object()
        evaluation_date = date(2026, 10, 1)
        evaluation = MagicMock(
            pk=7,
            cycle=cycle,
            pond=pond,
            evaluation_date=evaluation_date,
            mortality_quantity=0,
        )
        serializer = MagicMock()
        queryset = MagicMock()
        queryset.exclude.return_value.exists.return_value = False
        view = FishEvaluatedViewSet()

        with patch.object(view, "get_object", return_value=evaluation), patch.object(
            view, "get_serializer", return_value=serializer
        ), patch(
            "apps.monitoring.views.FishEvaluated.objects.filter",
            return_value=queryset,
        ):
            response = view.destroy(MagicMock())

        self.assertEqual(response.status_code, 204)
        serializer._refresh_cycle_control_stats_from.assert_called_once_with(
            cycle, pond, evaluation_date
        )
