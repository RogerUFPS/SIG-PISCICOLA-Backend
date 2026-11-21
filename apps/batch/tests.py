from datetime import date, timedelta

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.core.models import Alert, Unit
from apps.core.utils import ensure_overdue_events_alerts
from apps.cycle.models import Cycle, CyclePondBatch, ProductionPlan
from apps.cycle.services.lifecycle import finish_cycle
from apps.farms.models import City, Department, Farm
from apps.ponds.models import Pond
from apps.products.models import Product, Supplier, TypeProduct
from apps.purchases.models import Buy, PurchaseDetail
from apps.species.models import Specie

from .models import Batch, BatchSource, BatchTransfer, PondBatch


class BatchRouteIntegrationTests(TestCase):
    def setUp(self):
        admin_role = Role.objects.create(name="Admin")
        self.user = User.objects.create_user(
            email="admin-routes@example.com",
            password="test-password",
            role=admin_role,
            is_profile_complete=True,
        )
        department = Department.objects.create(name="Departamento rutas")
        city = City.objects.create(name="Ciudad rutas", department=department)
        self.farm = Farm.objects.create(
            name="Granja rutas",
            department=department,
            city=city,
            address="Prueba",
            total_area_ha=10,
        )
        self.specie = Specie.objects.create(
            name="Trucha rutas",
            description="",
            feeding_rate=2,
        )
        self.pond = Pond.objects.create(
            farm=self.farm,
            name="Estanque rutas",
            type=Pond.Type.CONCRETE,
            capacity=1000,
            area=100,
            volume=100,
            depth=1,
        )
        self.plan = ProductionPlan.objects.create(
            farm=self.farm,
            specie=self.specie,
            name="Plan rutas",
            type=ProductionPlan.Type.GROWOUT,
            total_days=90,
            expected_mortality_rate=1,
            expected_final_weight=300,
        )
        self.batch = Batch.objects.create(
            farm=self.farm,
            specie=self.specie,
            code="B-RUTAS",
            initial_quantity=100,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )
        self.pond_batch = PondBatch.objects.create(
            pond=self.pond,
            batch=self.batch,
            initial_quantity=100,
            current_quantity=100,
            start_date=date.today(),
        )
        self.cycle = Cycle.objects.create(
            farm=self.farm,
            pond=self.pond,
            specie=self.specie,
            production_plan=self.plan,
            name="Ciclo rutas",
            start_date=date.today(),
            estimated_finish_date=date.today() + timedelta(days=90),
            state=Cycle.State.IN_PROGRESS,
        )
        CyclePondBatch.objects.create(
            cycle=self.cycle,
            pond_batch=self.pond_batch,
            quantity=100,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_batch_cycles_returns_traceability_cycles(self):
        response = self.client.get(
            f"/api/farms/{self.farm.pk}/batches/{self.batch.pk}/cycles/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data], [self.cycle.pk])

    def test_batch_status_is_locked_during_active_cycle(self):
        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/batches/{self.batch.pk}/set-status/",
            {"status": Batch.Status.FINISHED},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, Batch.Status.ACTIVE)

    def test_batch_fields_are_locked_during_active_cycle(self):
        response = self.client.patch(
            f"/api/farms/{self.farm.pk}/batches/{self.batch.pk}/",
            {"comments": "Cambio manual"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unassigned_batch_can_be_split_before_pond_assignment(self):
        batch = Batch.objects.create(
            farm=self.farm,
            specie=self.specie,
            code="B-DIVISION-PREVIA",
            biological_state=Batch.BiologicalState.ALEVIN,
            initial_quantity=100,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )

        response = self.client.post(
            f"/api/farms/{self.farm.pk}/batches/{batch.pk}/split/",
            {"quantity": 30, "reason": "Separar para dos estanques"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        batch.refresh_from_db()
        self.assertEqual(batch.initial_quantity, 70)
        child = Batch.objects.get(pk=response.data["child_batch"]["id"])
        self.assertEqual(child.initial_quantity, 30)
        self.assertEqual(child.origin_type, Batch.OriginType.BATCH_SPLIT)
        link = BatchSource.objects.get(parent_batch=batch, child_batch=child)
        self.assertEqual(link.quantity, 30)
        self.assertEqual(response.data["original_quantity"], 100)
        self.assertEqual(response.data["retained_quantity"], 70)

        available = self.client.get(
            f"/api/farms/{self.farm.pk}/batches/?sin_estanque=true"
        )
        available_ids = [item["id"] for item in available.data]
        self.assertIn(batch.pk, available_ids)
        self.assertIn(child.pk, available_ids)

        traceability = self.client.get(
            f"/api/farms/{self.farm.pk}/batches/{child.pk}/traceability/"
        )
        self.assertEqual(traceability.status_code, 200)
        self.assertEqual(traceability.data["genealogy"][0]["parent_id"], batch.pk)
        self.assertEqual(traceability.data["genealogy"][0]["child_id"], child.pk)

    def test_assigned_batch_cannot_use_pre_assignment_split(self):
        response = self.client.post(
            f"/api/farms/{self.farm.pk}/batches/{self.batch.pk}/split/",
            {"quantity": 30, "reason": "Intento inválido"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("batch", response.data)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.initial_quantity, 100)

    def test_partial_first_pond_assignment_keeps_remainder_available(self):
        batch = Batch.objects.create(
            farm=self.farm,
            specie=self.specie,
            code="B-ASIGNACION-PARCIAL",
            biological_state=Batch.BiologicalState.ALEVIN,
            initial_quantity=100,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )
        destination = Pond.objects.create(
            farm=self.farm,
            name="Destino asignación parcial",
            type=Pond.Type.CONCRETE,
            capacity=500,
            area=100,
            volume=100,
            depth=1,
            status=Pond.Status.ACTIVE,
        )

        response = self.client.post(
            f"/api/farms/{self.farm.pk}/pond-batches/",
            {
                "pond": destination.pk,
                "batch": batch.pk,
                "initial_quantity": 60,
                "start_date": str(date.today()),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        batch.refresh_from_db()
        self.assertEqual(batch.initial_quantity, 60)
        self.assertEqual(response.data["current_quantity"], 60)
        split_result = response.data["split_result"]
        self.assertTrue(split_result["was_split"])
        self.assertEqual(split_result["assigned_quantity"], 60)
        self.assertEqual(split_result["remainder_quantity"], 40)
        child = Batch.objects.get(pk=split_result["remainder_batch"]["id"])
        self.assertEqual(child.initial_quantity, 40)
        self.assertFalse(PondBatch.objects.filter(batch=child).exists())
        link = BatchSource.objects.get(parent_batch=batch, child_batch=child)
        self.assertEqual(link.quantity, 40)

        available = self.client.get(
            f"/api/farms/{self.farm.pk}/batches/?sin_estanque=true"
        )
        available_ids = [item["id"] for item in available.data]
        self.assertNotIn(batch.pk, available_ids)
        self.assertIn(child.pk, available_ids)

        traceability = self.client.get(
            f"/api/farms/{self.farm.pk}/batches/{child.pk}/traceability/"
        )
        self.assertEqual(traceability.status_code, 200)
        self.assertEqual(traceability.data["genealogy"][0]["parent_id"], batch.pk)
        self.assertEqual(traceability.data["genealogy"][0]["child_id"], child.pk)

    def test_cycle_only_allows_estimated_finish_and_comments(self):
        detail_url = (
            f"/api/farms/{self.farm.pk}/ponds/{self.pond.pk}/"
            f"cycles/{self.cycle.pk}/"
        )
        rejected = self.client.patch(
            detail_url,
            {"start_date": str(date.today() - timedelta(days=1))},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400)
        state_rejected = self.client.patch(
            detail_url,
            {"state": Cycle.State.PAUSED},
            format="json",
        )
        self.assertEqual(state_rejected.status_code, 400)

        new_estimate = date.today() + timedelta(days=120)
        accepted = self.client.patch(
            detail_url,
            {
                "estimated_finish_date": str(new_estimate),
                "comments": "Estimación ajustada por crecimiento observado.",
            },
            format="json",
        )
        self.assertEqual(accepted.status_code, 200)
        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.estimated_finish_date, new_estimate)

    def test_active_cycle_cannot_be_deleted(self):
        response = self.client.delete(
            f"/api/farms/{self.farm.pk}/ponds/{self.pond.pk}/cycles/{self.cycle.pk}/"
        )
        self.assertEqual(response.status_code, 400)

    def test_cycle_can_finish_after_estimated_date(self):
        self.cycle.estimated_finish_date = date.today() - timedelta(days=1)
        self.cycle.save(update_fields=["estimated_finish_date"])

        finish_cycle(self.cycle, date.today())

        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.state, Cycle.State.FINISHED)
        self.assertEqual(self.cycle.finish_date, date.today())

    def test_cycle_batch_cannot_be_updated_or_unlinked(self):
        relation = CyclePondBatch.objects.get(cycle=self.cycle)
        url = (
            f"/api/farms/{self.farm.pk}/ponds/{self.pond.pk}/cycles/"
            f"{self.cycle.pk}/cycle-batches/{relation.pk}/"
        )
        self.assertEqual(
            self.client.patch(url, {"quantity": 50}, format="json").status_code,
            400,
        )
        self.assertEqual(self.client.delete(url).status_code, 405)

    def test_partial_cycle_assignment_splits_and_moves_remainder(self):
        source_batch = Batch.objects.create(
            farm=self.farm,
            specie=self.specie,
            code="B-PARCIAL",
            initial_quantity=100,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )
        source_assignment = PondBatch.objects.create(
            pond=self.pond,
            batch=source_batch,
            initial_quantity=100,
            current_quantity=100,
            start_date=date.today(),
        )
        destination = Pond.objects.create(
            farm=self.farm,
            name="Estanque remanente",
            type=Pond.Type.CONCRETE,
            capacity=500,
            area=100,
            volume=100,
            depth=1,
            status=Pond.Status.ACTIVE,
        )
        self.pond.status = Pond.Status.IN_USE
        self.pond.save(update_fields=["status"])

        response = self.client.post(
            (
                f"/api/farms/{self.farm.pk}/ponds/{self.pond.pk}/cycles/"
                f"{self.cycle.pk}/cycle-batches/"
            ),
            {
                "cycle": self.cycle.pk,
                "pond_batch": source_assignment.pk,
                "quantity": 60,
                "destination_pond": destination.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        source_assignment.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source_assignment.current_quantity, 60)
        child_link = BatchSource.objects.get(parent_batch=source_batch)
        self.assertEqual(child_link.quantity, 40)
        destination_assignment = PondBatch.objects.get(batch=child_link.child_batch)
        self.assertEqual(destination_assignment.pond, destination)
        self.assertEqual(destination_assignment.current_quantity, 40)
        self.assertEqual(destination.status, Pond.Status.IN_USE)
        self.assertTrue(
            BatchTransfer.objects.filter(
                source_pond_batch=source_assignment,
                to_pond_batch=destination_assignment,
                quantity=40,
            ).exists()
        )
        split_result = response.data["split_result"]
        self.assertTrue(split_result["was_split"])
        self.assertEqual(split_result["source_batch"]["id"], source_batch.pk)
        self.assertEqual(split_result["source_batch"]["quantity_in_cycle"], 60)
        self.assertEqual(
            split_result["remainder_batch"]["id"], child_link.child_batch_id
        )
        self.assertEqual(split_result["remainder_batch"]["quantity"], 40)
        self.assertEqual(split_result["remainder_batch"]["pond_id"], destination.pk)

        for batch_id in (source_batch.pk, child_link.child_batch_id):
            traceability = self.client.get(
                f"/api/farms/{self.farm.pk}/batches/{batch_id}/traceability/"
            )
            self.assertEqual(traceability.status_code, 200)
            self.assertEqual(len(traceability.data["genealogy"]), 1)
            genealogy = traceability.data["genealogy"][0]
            self.assertEqual(genealogy["parent_id"], source_batch.pk)
            self.assertEqual(genealogy["child_id"], child_link.child_batch_id)
            self.assertEqual(genealogy["quantity"], 40)

        source_pond_batches = self.client.get(
            f"/api/farms/{self.farm.pk}/pond-batches/?pond={self.pond.pk}"
        )
        destination_pond_batches = self.client.get(
            f"/api/farms/{self.farm.pk}/pond-batches/?pond={destination.pk}"
        )
        self.assertIn(
            source_assignment.pk,
            [item["id"] for item in source_pond_batches.data],
        )
        self.assertIn(
            destination_assignment.pk,
            [item["id"] for item in destination_pond_batches.data],
        )

    def test_partial_cycle_assignment_requires_destination(self):
        extra_batch = Batch.objects.create(
            farm=self.farm,
            specie=self.specie,
            code="B-SIN-DESTINO",
            initial_quantity=50,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )
        assignment = PondBatch.objects.create(
            pond=self.pond,
            batch=extra_batch,
            initial_quantity=50,
            current_quantity=50,
            start_date=date.today(),
        )
        self.pond.status = Pond.Status.IN_USE
        self.pond.save(update_fields=["status"])
        response = self.client.post(
            (
                f"/api/farms/{self.farm.pk}/ponds/{self.pond.pk}/cycles/"
                f"{self.cycle.pk}/cycle-batches/"
            ),
            {
                "cycle": self.cycle.pk,
                "pond_batch": assignment.pk,
                "quantity": 30,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("destination_pond", response.data)

    def test_pond_status_and_fields_are_locked_during_active_cycle(self):
        state_response = self.client.patch(
            f"/api/farms/{self.farm.pk}/ponds/{self.pond.pk}/inactivate/",
            format="json",
        )
        edit_response = self.client.patch(
            f"/api/farms/{self.farm.pk}/ponds/{self.pond.pk}/",
            {"description": "Cambio no permitido"},
            format="json",
        )

        self.assertEqual(state_response.status_code, 400)
        self.assertEqual(edit_response.status_code, 400)

    def test_estimated_finish_creates_and_resolves_non_blocking_alert(self):
        self.cycle.estimated_finish_date = date.today() - timedelta(days=1)
        self.cycle.save(update_fields=["estimated_finish_date"])

        ensure_overdue_events_alerts(self.farm.pk)
        alert = Alert.objects.get(
            source_type=Alert.SourceType.CYCLE,
            source_id=self.cycle.pk,
        )
        self.assertFalse(alert.is_resolved)

        self.cycle.estimated_finish_date = date.today() + timedelta(days=30)
        self.cycle.save(update_fields=["estimated_finish_date"])
        ensure_overdue_events_alerts(self.farm.pk)
        alert.refresh_from_db()
        self.assertTrue(alert.is_resolved)

    def test_traceability_endpoint_includes_cycle_and_growth_shape(self):
        response = self.client.get(
            f"/api/farms/{self.farm.pk}/batches/{self.batch.pk}/traceability/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["batch"]["id"], self.batch.pk)
        self.assertEqual(response.data["cycles"][0]["cycle_id"], self.cycle.pk)
        self.assertIn("origins", response.data)
        self.assertIn("growth", response.data)

    def test_traceability_identifies_purchase_supplier(self):
        unit = Unit.objects.create(name="Unidad", symbol="und")
        product_type = TypeProduct.objects.create(name="Lote")
        product = Product.objects.create(
            farm=self.farm,
            type_product=product_type,
            unit=unit,
            name="Alevinos trazables",
        )
        supplier = Supplier.objects.create(
            farm=self.farm,
            supplier_type=Supplier.SupplierType.JURIDICO,
            name="Proveedor de prueba",
            document_type=Supplier.DocumentType.NIT,
            document_number="900123456",
        )
        buy = Buy.objects.create(
            farm=self.farm,
            supplier=supplier,
            date=date.today(),
            invoice_number="FV-100",
        )
        detail = PurchaseDetail.objects.create(
            buy=buy,
            product=product,
            unit=unit,
            quantity=100,
            unit_value=10,
            total_value=1000,
        )
        self.batch.origin_type = Batch.OriginType.PURCHASE_DETAIL
        self.batch.origin_id = detail.pk
        self.batch.save(update_fields=["origin_type", "origin_id"])

        response = self.client.get(
            f"/api/farms/{self.farm.pk}/batches/{self.batch.pk}/traceability/"
        )

        self.assertEqual(response.status_code, 200)
        origin = response.data["origins"][0]
        self.assertEqual(origin["supplier"], supplier.name)
        self.assertEqual(origin["invoice_number"], "FV-100")

    def test_production_reports_include_traceability_in_pdf_and_excel(self):
        url = (
            f"/api/farms/{self.farm.pk}/batches/{self.batch.pk}/"
            "production-report/"
        )
        for export_format, content_type in (
            ("pdf", "application/pdf"),
            (
                "xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ):
            response = self.client.post(
                url,
                {"modules": ["biometry"], "format": export_format},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], content_type)
            self.assertGreater(len(response.content), 100)

    def test_batch_transfer_list_accepts_farm_keyword(self):
        response = self.client.get(
            f"/api/farms/{self.farm.pk}/batch-transfers/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_manual_batch_transfer_rejects_batch_in_active_cycle(self):
        destination = Pond.objects.create(
            farm=self.farm,
            name="Destino bloqueado",
            type=Pond.Type.CONCRETE,
            capacity=500,
            area=100,
            volume=100,
            depth=1,
            status=Pond.Status.ACTIVE,
        )
        response = self.client.post(
            f"/api/farms/{self.farm.pk}/batch-transfers/",
            {
                "source_pond_batch": self.pond_batch.pk,
                "destination_pond": destination.pk,
                "quantity": 20,
                "date": str(date.today()),
                "reason": "Movimiento no permitido",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("source_pond_batch", response.data)

    def test_manual_partial_transfer_creates_child_and_history(self):
        source_pond = Pond.objects.create(
            farm=self.farm,
            name="Origen manual parcial",
            type=Pond.Type.CONCRETE,
            capacity=500,
            area=100,
            volume=100,
            depth=1,
            status=Pond.Status.IN_USE,
        )
        destination = Pond.objects.create(
            farm=self.farm,
            name="Destino manual parcial",
            type=Pond.Type.CONCRETE,
            capacity=500,
            area=100,
            volume=100,
            depth=1,
            status=Pond.Status.ACTIVE,
        )
        batch = Batch.objects.create(
            farm=self.farm,
            specie=self.specie,
            code="B-MANUAL-PARCIAL",
            initial_quantity=80,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )
        source = PondBatch.objects.create(
            pond=source_pond,
            batch=batch,
            initial_quantity=80,
            current_quantity=80,
            start_date=date.today(),
        )

        response = self.client.post(
            f"/api/farms/{self.farm.pk}/batch-transfers/",
            {
                "source_pond_batch": source.pk,
                "destination_pond": destination.pk,
                "quantity": 30,
                "date": str(date.today()),
                "reason": "Redistribución por densidad",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.current_quantity, 50)
        self.assertIsNone(source.end_date)
        link = BatchSource.objects.get(parent_batch=batch)
        self.assertEqual(link.quantity, 30)
        destination_assignment = PondBatch.objects.get(batch=link.child_batch)
        self.assertEqual(destination_assignment.pond, destination)
        self.assertEqual(destination_assignment.current_quantity, 30)
        self.assertEqual(destination.status, Pond.Status.IN_USE)
        self.assertTrue(response.data["is_partial"])
        self.assertEqual(response.data["source_batch_id"], batch.pk)
        self.assertEqual(response.data["destination_batch_id"], link.child_batch_id)

        history = self.client.get(
            f"/api/farms/{self.farm.pk}/batch-transfers/"
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data[0]["destination_pond_id"], destination.pk)
        self.assertEqual(history.data[0]["quantity"], 30)

    def test_manual_full_transfer_moves_same_batch(self):
        source_pond = Pond.objects.create(
            farm=self.farm,
            name="Origen manual total",
            type=Pond.Type.CONCRETE,
            capacity=500,
            area=100,
            volume=100,
            depth=1,
            status=Pond.Status.IN_USE,
        )
        destination = Pond.objects.create(
            farm=self.farm,
            name="Destino manual total",
            type=Pond.Type.CONCRETE,
            capacity=500,
            area=100,
            volume=100,
            depth=1,
            status=Pond.Status.ACTIVE,
        )
        batch = Batch.objects.create(
            farm=self.farm,
            specie=self.specie,
            code="B-MANUAL-TOTAL",
            initial_quantity=80,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )
        source = PondBatch.objects.create(
            pond=source_pond,
            batch=batch,
            initial_quantity=80,
            current_quantity=80,
            start_date=date.today(),
        )

        response = self.client.post(
            f"/api/farms/{self.farm.pk}/batch-transfers/",
            {
                "source_pond_batch": source.pk,
                "destination_pond": destination.pk,
                "quantity": 80,
                "date": str(date.today()),
                "reason": "Cambio completo de estanque",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        source.refresh_from_db()
        source_pond.refresh_from_db()
        self.assertEqual(source.current_quantity, 0)
        self.assertEqual(source.end_date, date.today())
        destination_assignment = PondBatch.objects.get(
            pond=destination, batch=batch, end_date__isnull=True
        )
        self.assertEqual(destination_assignment.current_quantity, 80)
        self.assertEqual(source_pond.status, Pond.Status.ACTIVE)
        self.assertFalse(response.data["is_partial"])
        self.assertEqual(response.data["source_batch_id"], batch.pk)
        self.assertEqual(response.data["destination_batch_id"], batch.pk)
        self.assertFalse(BatchSource.objects.filter(parent_batch=batch).exists())
        active_at_source = self.client.get(
            f"/api/farms/{self.farm.pk}/pond-batches/?pond={source_pond.pk}&activos=true"
        )
        self.assertNotIn(source.pk, [item["id"] for item in active_at_source.data])
        source_history = self.client.get(
            f"/api/farms/{self.farm.pk}/pond-batches/?pond={source_pond.pk}"
        )
        history_item = next(
            item for item in source_history.data if item["id"] == source.pk
        )
        self.assertEqual(history_item["current_quantity"], 0)
        self.assertEqual(history_item["end_date"], str(date.today()))

    def test_manual_transfer_rejects_other_species_and_life_stage(self):
        source_pond = Pond.objects.create(
            farm=self.farm,
            name="Origen compatibilidad",
            type=Pond.Type.CONCRETE,
            capacity=500,
            area=100,
            volume=100,
            depth=1,
            status=Pond.Status.IN_USE,
        )
        source_batch = Batch.objects.create(
            farm=self.farm,
            specie=self.specie,
            code="B-COMPAT-ORIGEN",
            biological_state=Batch.BiologicalState.ALEVIN,
            initial_quantity=100,
            min_weight_g=10,
            avg_weight_g=12,
            max_weight_g=14,
        )
        source = PondBatch.objects.create(
            pond=source_pond,
            batch=source_batch,
            initial_quantity=100,
            current_quantity=100,
            start_date=date.today(),
        )
        other_specie = Specie.objects.create(
            name="Cachama negra",
            description="",
            feeding_rate=2,
        )

        scenarios = (
            ("Especie incompatible", other_specie, Batch.BiologicalState.ALEVIN),
            ("Etapa incompatible", self.specie, Batch.BiologicalState.RISING),
        )
        for index, (name, specie, biological_state) in enumerate(scenarios, start=1):
            destination = Pond.objects.create(
                farm=self.farm,
                name=name,
                type=Pond.Type.CONCRETE,
                capacity=500,
                area=100,
                volume=100,
                depth=1,
                status=Pond.Status.IN_USE,
            )
            resident_batch = Batch.objects.create(
                farm=self.farm,
                specie=specie,
                code=f"B-INCOMPATIBLE-{index}",
                biological_state=biological_state,
                initial_quantity=40,
                min_weight_g=10,
                avg_weight_g=12,
                max_weight_g=14,
            )
            PondBatch.objects.create(
                pond=destination,
                batch=resident_batch,
                initial_quantity=40,
                current_quantity=40,
                start_date=date.today(),
            )

            with self.subTest(name=name):
                response = self.client.post(
                    f"/api/farms/{self.farm.pk}/batch-transfers/",
                    {
                        "source_pond_batch": source.pk,
                        "destination_pond": destination.pk,
                        "quantity": 10,
                        "date": str(date.today()),
                        "reason": "Intento incompatible",
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("destination_pond", response.data)

        source.refresh_from_db()
        self.assertEqual(source.current_quantity, 100)
        self.assertFalse(BatchTransfer.objects.filter(source_pond_batch=source).exists())

    def test_grading_event_list_accepts_farm_keyword(self):
        response = self.client.get(
            f"/api/farms/{self.farm.pk}/grading-events/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_manual_grading_transfer_is_disabled(self):
        response = self.client.post(
            f"/api/farms/{self.farm.pk}/grading-events/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 405)
