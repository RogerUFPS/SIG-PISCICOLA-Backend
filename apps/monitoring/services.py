from typing import TYPE_CHECKING, Dict, Optional

from django.db.models import Avg, Max, Min, QuerySet, Sum

from apps.purchases.models import InventoryMovement

if TYPE_CHECKING:
    from .models import ControlStat


class BiomassCalculator:
    """
    Utility class for biomass-related calculations.
    """

    @staticmethod
    def calculate_biomass(live_quantity: int, avg_weight_g: float) -> float:
        """
        Calcula la biomasa en kg.
        biomasa = cantidad de peces vivos * peso promedio / 1000

        Args:
            live_quantity: Cantidad de peces vivos
            avg_weight_g: Peso promedio en gramos

        Returns:
            Biomasa en kilogramos
        """
        if live_quantity <= 0 or avg_weight_g <= 0:
            return 0.0
        return (live_quantity * avg_weight_g) / 1000

    @staticmethod
    def calculate_fca(
        feed_consumed_kg: float, biomass_gain_kg: float
    ) -> Optional[float]:
        """
        Calcula el Factor de Conversión Alimenticia (FCA).
        FCA = alimento consumido / ganancia de biomasa

        Args:
            feed_consumed_kg: Alimento consumido en kilogramos
            biomass_gain_kg: Ganancia de biomasa en kilogramos

        Returns:
            FCA o None si biomass_gain_kg <= 0 (no se puede dividir por 0 o negativo)
        """
        if biomass_gain_kg <= 0:
            return None
        if feed_consumed_kg <= 0:
            return None
        return feed_consumed_kg / biomass_gain_kg

    @staticmethod
    def calculate_biomass_gain(
        current_biomass_kg: float, previous_biomass_kg: float
    ) -> float:
        """
        Calcula la ganancia de biomasa.
        ganancia = biomasa actual - biomasa anterior

        Args:
            current_biomass_kg: Biomasa actual en kilogramos
            previous_biomass_kg: Biomasa anterior en kilogramos

        Returns:
            Ganancia de biomasa en kilogramos
        """
        return current_biomass_kg - previous_biomass_kg

    @staticmethod
    def get_cycle_initial_biomass(cycle_id: int) -> float:
        """Biomasa de la siembra inicial vinculada al ciclo, en kg."""
        from apps.cycle.models import CyclePondBatch

        rows = CyclePondBatch.objects.filter(cycle_id=cycle_id).values_list(
            "quantity", "pond_batch__batch__avg_weight_g"
        )
        return sum(
            (quantity * (avg_weight_g or 0) / 1000 for quantity, avg_weight_g in rows),
            0.0,
        )

    @staticmethod
    def get_sample_live_quantity(
        sampled_quantity: int, mortality_quantity: int = 0
    ) -> int:
        """Peces vivos en la muestra: evaluados menos mortalidad del muestreo."""
        return max(0, sampled_quantity - mortality_quantity)

    @staticmethod
    def get_pond_live_quantity(pond_id: int) -> int:
        """
        Cantidad de peces vivos en el estanque (stock operativo de lotes activos).
        """
        from apps.batch.models import PondBatch

        total = (
            PondBatch.objects.filter(pond_id=pond_id, end_date__isnull=True).aggregate(
                total=Sum("current_quantity")
            )["total"]
            or 0
        )
        return int(total)

    @staticmethod
    def get_cycle_pond_live_quantity(cycle_id: int, pond_id: int) -> int:
        """
        Cantidad viva operativa del ciclo en el estanque.
        """
        from apps.cycle.models import CyclePondBatch

        total = (
            CyclePondBatch.objects.filter(
                cycle_id=cycle_id,
                pond_batch__pond_id=pond_id,
                pond_batch__end_date__isnull=True,
            ).aggregate(total=Sum("pond_batch__current_quantity"))["total"]
            or 0
        )
        return int(total)

    @staticmethod
    def get_cycle_pond_total_quantity(cycle_id: int, pond_id: int) -> int:
        """
        Cantidad total de peces en lotes vinculados al ciclo/estanque.
        """
        from apps.cycle.models import CyclePondBatch

        total = (
            CyclePondBatch.objects.filter(
                cycle_id=cycle_id,
                pond_batch__pond_id=pond_id,
            ).aggregate(total=Sum("quantity"))["total"]
            or 0
        )
        return int(total)

    @staticmethod
    def calculate_control_biomass(
        cycle_id: int,
        pond_id: int,
        avg_weight_g: float,
        mortality_quantity: int = 0,
        fallback_live_quantity: int = 0,
    ) -> tuple[int, float]:

        live_quantity = BiomassCalculator.get_cycle_pond_live_quantity(
            cycle_id, pond_id
        )
        if live_quantity <= 0:
            live_quantity = max(0, fallback_live_quantity)

        biomass_kg = BiomassCalculator.calculate_biomass(live_quantity, avg_weight_g)
        return live_quantity, biomass_kg

    @staticmethod
    def get_previous_control_stat(
        cycle_id: int, pond_id: int, control_date
    ) -> Optional["ControlStat"]:
        """
        ControlStat de referencia para calcular ganancia de biomasa.

        - Si ya hay un control en la misma fecha, se usa ese (evaluación anterior del día).
        - Si no, el control inmediatamente anterior por fecha.
        """
        from .models import ControlStat

        same_day = ControlStat.objects.filter(
            cycle_id=cycle_id,
            pond_id=pond_id,
            control_date=control_date,
            deleted_at__isnull=True,
        ).first()
        if same_day:
            return same_day

        return (
            ControlStat.objects.filter(
                cycle_id=cycle_id,
                pond_id=pond_id,
                control_date__lt=control_date,
                deleted_at__isnull=True,
            )
            .order_by("-control_date")
            .first()
        )

    @staticmethod
    def get_active_pond_weights(pond_id: int) -> Dict:
        """
        Obtiene los pesos (min, avg, max) de los lotes activos en un estanque.
        Basado en los PondBatch activos (sin fecha de fin) del estanque.

        Args:
            pond_id: ID del estanque

        Returns:
            Dict con:
            - min_weight_g: Peso mínimo de los lotes activos
            - avg_weight_g: Peso promedio (promedio de promedios)
            - max_weight_g: Peso máximo de los lotes activos

            Si no hay lotes activos, retorna ceros
        """
        from apps.batch.models import PondBatch

        # Obtener todos los lotes activos en el estanque
        active_pond_batches = PondBatch.objects.filter(
            pond_id=pond_id, end_date__isnull=True
        ).select_related("batch")

        if not active_pond_batches.exists():
            return {
                "min_weight_g": 0.0,
                "avg_weight_g": 0.0,
                "max_weight_g": 0.0,
            }

        # Calcular los pesos agregados
        weights = active_pond_batches.aggregate(
            min_weight=Min("batch__min_weight_g"),
            max_weight=Max("batch__max_weight_g"),
            avg_weight=Avg("batch__avg_weight_g"),
        )

        return {
            "min_weight_g": weights["min_weight"] or 0.0,
            "avg_weight_g": weights["avg_weight"] or 0.0,
            "max_weight_g": weights["max_weight"] or 0.0,
        }


class FishEvaluatedCalculator:
    """
    Utility class for aggregating fish evaluations.
    """

    @staticmethod
    def aggregate_fish_evaluations(evaluations: QuerySet) -> Dict:
        """
        Agrega múltiples FishEvaluated para obtener estadísticas consolidadas.

        Args:
            evaluations: QuerySet de FishEvaluated

        Returns:
            Dict con estadísticas consolidadas:
            - sampled_quantity: Total de peces evaluados
            - live_quantity: Total de peces vivos
            - min_weight_g: Peso mínimo
            - avg_weight_g: Peso promedio
            - max_weight_g: Peso máximo
            - mortality_percentage: Porcentaje de mortalidad
        """
        if not evaluations.exists():
            return {
                "sampled_quantity": 0,
                "live_quantity": 0,
                "min_weight_g": 0.0,
                "avg_weight_g": 0.0,
                "max_weight_g": 0.0,
                "mortality_percentage": 0.0,
            }

        # Agregaciones
        aggregation = evaluations.aggregate(
            total_sampled=Sum("sampled_quantity"),
            total_mortality=Sum("mortality_quantity"),
            min_weight=Min("min_weight_g"),
            max_weight=Max("max_weight_g"),
            avg_weight_avg=Avg("avg_weight_g"),
        )

        sampled_quantity = aggregation["total_sampled"] or 0
        total_mortality = aggregation["total_mortality"] or 0
        live_quantity = sampled_quantity - total_mortality

        mortality_percentage = (
            (total_mortality / sampled_quantity * 100) if sampled_quantity > 0 else 0.0
        )

        return {
            "sampled_quantity": sampled_quantity,
            "live_quantity": live_quantity,
            "min_weight_g": aggregation["min_weight"] or 0.0,
            "avg_weight_g": aggregation["avg_weight_avg"] or 0.0,
            "max_weight_g": aggregation["max_weight"] or 0.0,
            "mortality_percentage": mortality_percentage,
        }


class CycleStateCalculator:
    """
    Utility class for calculating the current dynamic state of a cycle based on monitoring data.
    """

    @staticmethod
    def get_cycle_current_state(cycle_id: int) -> Dict:
        """
        Calcula el estado actual dinámico de un ciclo basándose en los datos registrados en monitoring.

        El estado incluye:
        - fish_quantity: Cantidad actual de peces vivos
        - total_mortality: Total de peces muertos
        - avg_weight_g: Peso promedio actual
        - min_weight_g: Peso mínimo registrado
        - max_weight_g: Peso máximo registrado
        - mortality_percentage: Porcentaje de mortalidad
        - biomass_kg: Biomasa total actual
        - fca: Factor de conversión alimenticia (si hay datos suficientes)
        - has_monitoring_data: Si hay al menos 1 evaluación de peces

        Args:
            cycle_id: ID del ciclo

        Returns:
            Dict con el estado actual del ciclo
        """
        from .models import ControlStat, FishEvaluated

        # Obtener todas las evaluaciones de peces del ciclo (no eliminadas)
        evaluations = FishEvaluated.objects.filter(
            cycle_id=cycle_id, deleted_at__isnull=True
        ).order_by("-evaluation_date")

        if not evaluations.exists():
            return {
                "fish_quantity": 0,
                "total_mortality": 0,
                "avg_weight_g": 0.0,
                "min_weight_g": 0.0,
                "max_weight_g": 0.0,
                "mortality_percentage": 0.0,
                "biomass_kg": 0.0,
                "fca": None,
                "has_monitoring_data": False,
                "days_elapsed": 0,
            }

        # Obtener la evaluación más reciente
        latest_evaluation = evaluations.first()

        # Agregaciones de todas las evaluaciones
        aggregation = evaluations.aggregate(
            total_sampled=Sum("sampled_quantity"),
            total_mortality=Sum("mortality_quantity"),
            min_weight=Min("min_weight_g"),
            max_weight=Max("max_weight_g"),
            avg_weight_avg=Avg("avg_weight_g"),
        )

        sampled_quantity = aggregation["total_sampled"] or 0
        total_mortality = aggregation["total_mortality"] or 0
        sample_live_quantity = sampled_quantity - total_mortality

        avg_weight_g = latest_evaluation.avg_weight_g
        live_quantity, biomass_kg = BiomassCalculator.calculate_control_biomass(
            cycle_id,
            latest_evaluation.pond_id,
            avg_weight_g,
            mortality_quantity=total_mortality,
            fallback_live_quantity=sample_live_quantity,
        )

        total_fish_seen = live_quantity + total_mortality
        mortality_percentage = (
            (total_mortality / total_fish_seen * 100) if total_fish_seen > 0 else 0.0
        )

        # Calcular FCA usando el último control y el alimento efectivo acumulado.
        fca = None
        biomass_gain_kg = None
        control_stats = ControlStat.objects.filter(
            cycle_id=cycle_id, deleted_at__isnull=True
        ).order_by("-control_date")

        latest_control = control_stats.first()
        if latest_control:
            biomass_gain_kg = latest_control.biomass_gain_kg
            fca = latest_control.fca

            if fca is None and biomass_gain_kg is not None:
                from apps.feeding.utils import cycle_feed_consumed_kg

                feed_kg = cycle_feed_consumed_kg(
                    cycle_id=cycle_id,
                    end_date=latest_control.control_date,
                )
                fca = BiomassCalculator.calculate_fca(
                    float(feed_kg), biomass_gain_kg
                )

        # Calcular días desde el inicio del ciclo
        from apps.cycle.models import Cycle

        cycle = Cycle.objects.get(id=cycle_id)
        days_elapsed = (latest_evaluation.evaluation_date - cycle.start_date).days

        return {
            "fish_quantity": live_quantity,
            "total_mortality": total_mortality,
            "avg_weight_g": avg_weight_g,
            "min_weight_g": latest_evaluation.min_weight_g,
            "max_weight_g": latest_evaluation.max_weight_g,
            "mortality_percentage": mortality_percentage,
            "biomass_kg": biomass_kg,
            "biomass_gain_kg": biomass_gain_kg,
            "fca": fca,
            "has_monitoring_data": True,
            "days_elapsed": days_elapsed,
            "last_evaluation_date": latest_evaluation.evaluation_date,
        }

    @staticmethod
    def has_monitoring_data(cycle_id: int) -> bool:
        """
        Verifica si un ciclo tiene datos de monitoring registrados.

        Retorna True si hay al menos 1 FishEvaluated, DailyStat, o ControlStat.

        Args:
            cycle_id: ID del ciclo

        Returns:
            True si hay datos de monitoring, False en caso contrario
        """
        from .models import ControlStat, DailyStat, FishEvaluated

        has_fish_eval = FishEvaluated.objects.filter(
            cycle_id=cycle_id, deleted_at__isnull=True
        ).exists()

        has_daily = DailyStat.objects.filter(
            cycle_id=cycle_id, deleted_at__isnull=True
        ).exists()

        has_control = ControlStat.objects.filter(
            cycle_id=cycle_id, deleted_at__isnull=True
        ).exists()

        return has_fish_eval or has_daily or has_control


__all__ = ["BiomassCalculator", "FishEvaluatedCalculator", "CycleStateCalculator"]
