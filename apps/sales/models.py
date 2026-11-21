# models.py
import datetime

from django.conf import settings
from django.db import models

from apps.farms.models import Farm
from apps.harvest.models import HarvestClassification


class Client(models.Model):

    class ClientType(models.TextChoices):
        NATURAL = "natural", "Natural"
        JURIDICO = "juridico", "Jurídico"

    class DocumentType(models.TextChoices):
        CE = "CE", "Cédula de Extranjería"
        CC = "CC", "Cédula de Ciudadanía"
        PAS = "PAS", "Pasaporte"
        NIT = "NIT", "NIT"
        PPT = "PPT", "Permiso por Protección Temporal"

    farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="clients",
        verbose_name="Finca",
    )
    client_type = models.CharField(
        max_length=20,
        choices=ClientType.choices,
        verbose_name="Tipo de cliente",
    )
    name = models.CharField(max_length=255, verbose_name="Nombre")
    document_type = models.CharField(
        max_length=10,
        choices=DocumentType.choices,
        verbose_name="Tipo de documento",
    )
    document_number = models.CharField(
        max_length=50,
        verbose_name="Número de documento",
    )
    phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="Teléfono",
    )
    email = models.EmailField(
        blank=True,
        default="",
        verbose_name="Correo electrónico",
    )
    address = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Dirección",
    )
    observations = models.TextField(
        blank=True,
        default="",
        verbose_name="Observaciones",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado en")

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "document_type", "document_number"],
                name="unique_client_document_per_farm",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.document_type}: {self.document_number})"


class Sale(models.Model):

    class PaymentMethod(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TRANSFERENCIA = "transferencia", "Transferencia"

    farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="sales",
        verbose_name="Finca",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
        verbose_name="Cliente",
    )
    invoice_number = models.CharField(
        max_length=100,
        verbose_name="Número de factura",
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        verbose_name="Método de pago",
    )
    observations = models.TextField(
        blank=True,
        default="",
        verbose_name="Observaciones",
    )
    date = models.DateField(
        verbose_name="Fecha",
        default=datetime.date.today,
    )
    total = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=0,
        verbose_name="Total",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales_created",
        verbose_name="Creado por",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado en")

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"

    def __str__(self):
        return f"Venta #{self.invoice_number} — {self.date}"


class SaleDetail(models.Model):
    farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="sale_details",
        verbose_name="Finca",
    )
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="details",
        verbose_name="Venta",
    )
    harvest_classification = models.ForeignKey(
        HarvestClassification,
        on_delete=models.PROTECT,
        related_name="sale_details",
        verbose_name="Clasificación de cosecha",
    )
    quantity_g = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="Cantidad (g)",
    )
    fish_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Cantidad de peces",
    )
    price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Precio total del detalle",
    )

    class Meta:
        verbose_name = "Detalle de venta"
        verbose_name_plural = "Detalles de venta"

    def __str__(self):
        return (
            f"Detalle #{self.pk} — Venta #{self.sale_id} "
            f"| {self.harvest_classification} x {self.quantity_g} g"
        )

    @property
    def subtotal(self):
        return self.quantity_g * self.price
