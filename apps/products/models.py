from django.db import models


class TypeProduct(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "type_product"

    def __str__(self):
        return self.name


class Product(models.Model):
    type_product = models.ForeignKey(
        TypeProduct, on_delete=models.PROTECT, related_name="products"
    )
    farm = models.ForeignKey(
        "farms.Farm", on_delete=models.CASCADE, related_name="products"
    )
    unit = models.ForeignKey(
        "core.Unit", on_delete=models.PROTECT, related_name="products"
    )
    name = models.CharField(max_length=255)
    comments = models.TextField(blank=True)
    minimun_stock_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "product"
        constraints = [
            models.UniqueConstraint(
                fields=["name", "farm"], name="uq_product_name_farm"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.farm})"


class Supplier(models.Model):
    class SupplierType(models.TextChoices):
        NATURAL = "natural", "Natural"
        JURIDICO = "juridico", "Jurídico"

    class DocumentType(models.TextChoices):
        CE = "CE", "Cédula de Extranjería"
        CC = "CC", "Cédula de Ciudadanía"
        PAS = "PAS", "Pasaporte"
        NIT = "NIT", "NIT"

    farm = models.ForeignKey(
        "farms.Farm", on_delete=models.CASCADE, related_name="suppliers"
    )
    supplier_type = models.CharField(max_length=20, choices=SupplierType.choices)
    name = models.CharField(max_length=255)
    document_type = models.CharField(max_length=5, choices=DocumentType.choices)
    document_number = models.CharField(max_length=50)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    observations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "supplier"
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "document_type", "document_number"],
                name="uq_supplier_farm_document",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.document_type} {self.document_number})"
