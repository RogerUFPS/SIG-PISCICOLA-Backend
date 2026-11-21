from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase
from rest_framework import serializers, status

from apps.purchases.models import InventoryMovement
from apps.products.serializers import SupplierSerializer
from apps.products.views import ProductViewSet


class SupplierPhoneValidationTests(SimpleTestCase):
    def test_accepts_valid_colombian_phone(self):
        self.assertEqual(
            SupplierSerializer().validate_phone("3227174462"), "3227174462"
        )

    def test_accepts_longer_international_phone(self):
        phone = "+57 (322) 717-4462"
        self.assertEqual(SupplierSerializer().validate_phone(phone), phone)

    def test_accepts_up_to_fifteen_digits(self):
        phone = "123456789012345"
        self.assertEqual(SupplierSerializer().validate_phone(phone), phone)

    def test_allows_blank_phone(self):
        self.assertEqual(SupplierSerializer().validate_phone(""), "")

    def test_rejects_invalid_phone_lengths_and_characters(self):
        for phone in ("123456", "1234567890123456", "30012345ab"):
            with self.subTest(phone=phone):
                with self.assertRaises(serializers.ValidationError):
                    SupplierSerializer().validate_phone(phone)


class ProductDeletionTests(SimpleTestCase):
    def test_rejects_deletion_after_outgoing_inventory_movement(self):
        product = MagicMock()
        view = ProductViewSet()
        view.get_object = MagicMock(return_value=product)
        movements = MagicMock()
        movements.exists.return_value = True

        with (
            patch(
                "apps.products.views.InventoryMovement.objects.filter",
                return_value=movements,
            ) as filter_movements,
            patch("apps.products.views.soft_delete") as soft_delete,
        ):
            response = view.destroy(RequestFactory().delete("/"), pk=product.pk)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            {"detail": "No se puede eliminar un producto que ya fue utilizado."},
        )
        filter_movements.assert_called_once_with(
            product=product,
            movement_type=InventoryMovement.MovementType.OUT,
        )
        soft_delete.assert_not_called()

    def test_soft_deletes_product_without_outgoing_movements(self):
        product = MagicMock()
        view = ProductViewSet()
        view.get_object = MagicMock(return_value=product)
        movements = MagicMock()
        movements.exists.return_value = False

        with (
            patch(
                "apps.products.views.InventoryMovement.objects.filter",
                return_value=movements,
            ),
            patch("apps.products.views.soft_delete") as soft_delete,
        ):
            response = view.destroy(RequestFactory().delete("/"), pk=product.pk)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        soft_delete.assert_called_once_with(product)
