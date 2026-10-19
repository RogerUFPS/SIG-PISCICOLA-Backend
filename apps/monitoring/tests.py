from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.monitoring.services import BiomassCalculator


class BiomassIndicatorTests(SimpleTestCase):
    def test_initial_biomass_uses_cycle_stocking_quantity_and_initial_weight(self):
        rows = MagicMock()
        rows.values_list.return_value = [(495, 1.01)]

        with patch(
            "apps.cycle.models.CyclePondBatch.objects.filter",
            return_value=rows,
        ):
            initial_biomass = BiomassCalculator.get_cycle_initial_biomass(39)

        self.assertAlmostEqual(initial_biomass, 0.49995)

    def test_gain_and_fca_use_initial_biomass(self):
        current_biomass = 9.9
        initial_biomass = 0.5
        feed_consumed = 12.0

        gain = BiomassCalculator.calculate_biomass_gain(
            current_biomass,
            initial_biomass,
        )
        fca = BiomassCalculator.calculate_fca(feed_consumed, gain)

        self.assertAlmostEqual(gain, 9.4)
        self.assertAlmostEqual(fca, 12 / 9.4)
