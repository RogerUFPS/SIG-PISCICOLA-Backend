from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework import serializers

from apps.cycle.models import Cycle

from .models import FeedingEvent
from .serializers import FeedingEventUpdateSerializer
from .utils import (
    active_plan_date_overlap,
    collect_feeding_plan_business_errors,
    planned_feed_quantity_per_ration,
)


class FeedingPlanValidationTests(SimpleTestCase):
    def _entities(self, *, stage="alevin"):
        farm = SimpleNamespace(pk=1, deleted_at=None)
        cycle = SimpleNamespace(
            pk=2,
            farm_id=1,
            farm=farm,
            specie_id=3,
            state=Cycle.State.IN_PROGRESS,
            start_date=date(2026, 1, 1),
            estimated_finish_date=date(2026, 12, 31),
            finish_date=None,
            deleted_at=None,
        )
        schedule = SimpleNamespace(
            farm_id=1,
            farm=farm,
            specie_id=3,
            type=stage,
            deleted_at=None,
        )
        return cycle, schedule

    @patch("apps.feeding.utils.Farm.objects.get")
    @patch("apps.feeding.utils.CyclePondBatch.objects.filter")
    def test_rejects_schedule_from_another_biological_stage(
        self, cycle_batches_filter, farm_get
    ):
        cycle, schedule = self._entities(stage="fatting")
        cycle_batches_filter.return_value.values_list.return_value = ["alevin"]

        errors = collect_feeding_plan_business_errors(
            farm_id=1,
            cycle=cycle,
            schedule=schedule,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )

        self.assertIn("feeding_schedule", errors)
        self.assertIn("etapa biológica", errors["feeding_schedule"])
        farm_get.assert_called_once()

    @patch("apps.feeding.utils.Farm.objects.get")
    @patch("apps.feeding.utils.CyclePondBatch.objects.filter")
    def test_accepts_schedule_matching_biological_stage(
        self, cycle_batches_filter, farm_get
    ):
        cycle, schedule = self._entities(stage="alevin")
        cycle_batches_filter.return_value.values_list.return_value = ["alevin"]

        errors = collect_feeding_plan_business_errors(
            farm_id=1,
            cycle=cycle,
            schedule=schedule,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )

        self.assertNotIn("feeding_schedule", errors)

    @patch("apps.feeding.utils.Farm.objects.get")
    @patch("apps.feeding.utils.CyclePondBatch.objects.filter")
    def test_rejects_plan_when_cycle_has_no_stage_to_validate(
        self, cycle_batches_filter, farm_get
    ):
        cycle, schedule = self._entities(stage="alevin")
        cycle_batches_filter.return_value.values_list.return_value = []

        errors = collect_feeding_plan_business_errors(
            farm_id=1,
            cycle=cycle,
            schedule=schedule,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )

        self.assertIn("no tiene un lote asociado", errors["feeding_schedule"])

    @patch("apps.feeding.utils.FeedingPlan.objects.filter")
    def test_detects_inclusive_overlap_in_same_cycle(self, plan_filter):
        plan_filter.return_value.exists.return_value = True

        self.assertTrue(
            active_plan_date_overlap(
                cycle_id=8,
                start_date=date(2026, 3, 10),
                end_date=date(2026, 3, 20),
            )
        )
        plan_filter.assert_called_once_with(
            cycle_id=8,
            deleted_at__isnull=True,
            start_date__lte=date(2026, 3, 20),
            end_date__gte=date(2026, 3, 10),
        )


class FeedingRationPrecisionTests(SimpleTestCase):
    def test_preserves_six_decimals_for_small_ration(self):
        result = planned_feed_quantity_per_ration(
            fish_count=Decimal("500"),
            avg_weight_g=Decimal("1"),
            feeding_rate_percentage=Decimal("3.5"),
            times_per_day=3,
        )

        self.assertEqual(result, Decimal("0.005833"))


class ConfirmedFeedingEventTests(SimpleTestCase):
    def test_rejects_direct_changes_to_completed_event(self):
        event = SimpleNamespace(
            status=FeedingEvent.Status.COMPLETED,
            cycle=SimpleNamespace(state=Cycle.State.IN_PROGRESS),
            feeding_plan=SimpleNamespace(
                deleted_at=None,
                start_date=date(2026, 1, 1),
                end_date=date(2099, 12, 31),
            ),
        )
        serializer = FeedingEventUpdateSerializer(instance=event, partial=True)

        with self.assertRaises(serializers.ValidationError) as exc:
            serializer.validate({"actual_quantity": Decimal("1.25")})

        self.assertIn("suministro confirmado", str(exc.exception))


class FeedingEventPlanLifecycleTests(SimpleTestCase):
    def _scheduled_event(self, *, end_date, deleted_at=None):
        return SimpleNamespace(
            status=FeedingEvent.Status.SCHEDULED,
            cycle=SimpleNamespace(state=Cycle.State.IN_PROGRESS),
            feeding_plan=SimpleNamespace(
                deleted_at=deleted_at,
                start_date=date(2026, 1, 1),
                end_date=end_date,
            ),
        )

    def test_rejects_feeding_when_plan_has_finished(self):
        event = self._scheduled_event(end_date=date(2026, 1, 31))
        serializer = FeedingEventUpdateSerializer(instance=event, partial=True)

        with self.assertRaises(serializers.ValidationError) as exc:
            serializer.validate(
                {
                    "status": FeedingEvent.Status.COMPLETED,
                    "actual_quantity": Decimal("1.25"),
                    "actual_unit": SimpleNamespace(pk=1),
                }
            )

        self.assertIn("plan que ya finalizó", str(exc.exception))

    def test_rejects_feeding_when_plan_is_archived(self):
        event = self._scheduled_event(
            end_date=date(2099, 12, 31),
            deleted_at=SimpleNamespace(),
        )
        serializer = FeedingEventUpdateSerializer(instance=event, partial=True)

        with self.assertRaises(serializers.ValidationError) as exc:
            serializer.validate(
                {
                    "status": FeedingEvent.Status.COMPLETED,
                    "actual_quantity": Decimal("1.25"),
                    "actual_unit": SimpleNamespace(pk=1),
                }
            )

        self.assertIn("plan archivado", str(exc.exception))
