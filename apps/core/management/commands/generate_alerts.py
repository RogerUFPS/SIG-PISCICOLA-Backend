from apps.core.models import Alert
from apps.core.signals import audit_queryset_update
from apps.feeding.models import FeedingEvent
from apps.health.models import TreatmentEvent
from apps.monitoring.models import FishEvaluated
from apps.products.models import Product
from apps.purchases.utils import get_product_stock
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

THRESHOLDS = [5, 10, 15, 20, 25]


def _resolve_alerts(qs):
    if not qs.exists():
        return
    audit_queryset_update(qs, is_resolved=True, resolved_at=timezone.now())


class Command(BaseCommand):
    help = "Generate minimal alerts: stock low, mortality thresholds, feeding/treatment overdue"

    def add_arguments(self, parser):
        parser.add_argument("--farm-id", type=int, help="Limit to a single farm id")

    def handle(self, *args, **options):
        farm_id = options.get("farm_id")
        today = timezone.now().date()

        self.stdout.write("Generating alerts...")

        # 1) Stock low alerts (products)
        products = Product.objects.filter(deleted_at__isnull=True)
        if farm_id:
            products = products.filter(farm_id=farm_id)

        for product in products:
            try:
                stock = get_product_stock(product.id, product.farm_id)
            except Exception:
                continue

            existing_qs = Alert.objects.filter(
                farm=product.farm,
                source_type=Alert.SourceType.STOCK,
                source_id=product.id,
                is_resolved=False,
            )

            if float(stock) < float(product.minimun_stock_threshold or 0):
                if not existing_qs.exists():
                    Alert.objects.create(
                        farm=product.farm,
                        source_type=Alert.SourceType.STOCK,
                        source_id=product.id,
                        description=f"Stock bajo para producto {product.name}",
                        message=f"Stock {stock} < threshold {product.minimun_stock_threshold}",
                        value=float(stock),
                        threshold=float(product.minimun_stock_threshold or 0),
                        severity=Alert.Severity.MEDIUM,
                    )
            else:
                # resolve existing stock alerts for this product
                _resolve_alerts(existing_qs)

        # 2) Mortality thresholds per (cycle, pond) using latest FishEvaluated
        pairs = (
            FishEvaluated.objects.filter(deleted_at__isnull=True)
            .values("cycle_id", "pond_id")
            .distinct()
        )
        for p in pairs:
            cycle_id = p["cycle_id"]
            pond_id = p["pond_id"]
            latest = (
                FishEvaluated.objects.filter(
                    cycle_id=cycle_id, pond_id=pond_id, deleted_at__isnull=True
                )
                .order_by("-evaluation_date")
                .first()
            )
            if not latest or latest.sampled_quantity <= 0:
                continue

            mortality_pct = latest.mortality_quantity / latest.sampled_quantity * 100.0
            reached = None
            for t in THRESHOLDS:
                if mortality_pct >= t:
                    reached = t

            existing_qs = Alert.objects.filter(
                farm=latest.farm,
                pond_id=pond_id,
                cycle_id=cycle_id,
                source_type=Alert.SourceType.HEALTH,
                is_resolved=False,
            )

            if reached is None:
                _resolve_alerts(existing_qs)
            else:
                # check if existing alert already at same or higher threshold
                existing = existing_qs.order_by("-threshold").first()
                if existing and (existing.threshold or 0) >= reached:
                    # already reported
                    continue
                # resolve older lower-threshold alerts
                _resolve_alerts(existing_qs)
                Alert.objects.create(
                    farm=latest.farm,
                    pond_id=pond_id,
                    cycle_id=cycle_id,
                    source_type=Alert.SourceType.HEALTH,
                    source_id=latest.id,
                    description=f"Mortalidad en estanque {pond_id} ciclo {cycle_id}",
                    message=f"Mortalidad {mortality_pct:.2f}% >= {reached}%",
                    value=float(mortality_pct),
                    threshold=float(reached),
                    severity=(
                        Alert.Severity.HIGH if reached >= 15 else Alert.Severity.MEDIUM
                    ),
                )

        # 3) FeedingEvent overdue
        feeding_qs = FeedingEvent.objects.filter(
            date__lte=today, status=FeedingEvent.Status.SCHEDULED
        )
        if farm_id:
            feeding_qs = feeding_qs.filter(farm_id=farm_id)
        for ev in feeding_qs:
            existing = Alert.objects.filter(
                farm=ev.farm,
                source_type=Alert.SourceType.FEEDING,
                source_id=ev.id,
                is_resolved=False,
            )
            if not existing.exists():
                Alert.objects.create(
                    farm=ev.farm,
                    pond=ev.pond,
                    cycle=ev.cycle,
                    source_type=Alert.SourceType.FEEDING,
                    source_id=ev.id,
                    description=f"FeedingEvent pendiente ({ev.id})",
                    message=f"Evento programado para {ev.date} no cumplido.",
                    severity=Alert.Severity.MEDIUM,
                )

        # resolve feeding alerts for completed events
        completed_feed_qs = FeedingEvent.objects.exclude(
            status=FeedingEvent.Status.SCHEDULED
        )
        for ev in completed_feed_qs:
            audit_queryset_update(
                Alert.objects.filter(
                    source_type=Alert.SourceType.FEEDING,
                    source_id=ev.id,
                    is_resolved=False,
                ),
                is_resolved=True,
                resolved_at=timezone.now(),
            )

        # 4) TreatmentEvent overdue
        treatment_qs = TreatmentEvent.objects.filter(
            date__lte=today, status=TreatmentEvent.Status.SCHEDULED
        )
        if farm_id:
            treatment_qs = treatment_qs.filter(farm_id=farm_id)
        for ev in treatment_qs:
            existing = Alert.objects.filter(
                farm=ev.farm,
                source_type=Alert.SourceType.HEALTH,
                source_id=ev.id,
                is_resolved=False,
            )
            if not existing.exists():
                Alert.objects.create(
                    farm=ev.farm,
                    pond=ev.pond,
                    cycle=ev.cycle,
                    source_type=Alert.SourceType.HEALTH,
                    source_id=ev.id,
                    description=f"TreatmentEvent pendiente ({ev.id})",
                    message=f"Evento de tratamiento programado para {ev.date} no cumplido.",
                    severity=Alert.Severity.MEDIUM,
                )

        # resolve treatment alerts for completed events
        completed_treat_qs = TreatmentEvent.objects.exclude(
            status=TreatmentEvent.Status.SCHEDULED
        )
        for ev in completed_treat_qs:
            audit_queryset_update(
                Alert.objects.filter(
                    source_type=Alert.SourceType.HEALTH,
                    source_id=ev.id,
                    is_resolved=False,
                ),
                is_resolved=True,
                resolved_at=timezone.now(),
            )

        self.stdout.write("Alerts generation complete.")
