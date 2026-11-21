# models.py
from django.db import models


class Buy(models.Model):
    farm = models.ForeignKey(
        "farms.Farm", on_delete=models.CASCADE, related_name="buys"
    )
    supplier = models.ForeignKey(
        "products.Supplier",
        on_delete=models.SET_NULL,
        related_name="buys",
        null=True,
        blank=True,
    )
    date = models.DateField()
    invoice_number = models.CharField(max_length=100, blank=True)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "buy"
        ordering = ["-date"]

    def __str__(self):
        return f"Buy {self.id} - {self.farm} ({self.date})"


class PurchaseDetail(models.Model):
    buy = models.ForeignKey(Buy, on_delete=models.CASCADE, related_name="details")
    product = models.ForeignKey(
        "products.Product", on_delete=models.PROTECT, related_name="purchase_details"
    )
    unit = models.ForeignKey(
        "core.Unit", on_delete=models.PROTECT, related_name="purchase_details"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    unit_value = models.DecimalField(max_digits=12, decimal_places=2)
    total_value = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchase_detail"

    def __str__(self):
        return f"PurchaseDetail {self.id} - {self.product} x{self.quantity}"


class InventoryMovement(models.Model):
    class MovementType(models.TextChoices):
        IN = "In", "Entrada"
        OUT = "Out", "Salida"
        INITIAL = "Initial", "Inicial"

    class SourceType(models.TextChoices):
        PURCHASE = "Purchase", "Compra"
        FEEDING = "Feeding", "Alimentación"
        HEALTH = "Health", "Salud"
        DAILY = "Daily", "Diario"

    farm = models.ForeignKey(
        "farms.Farm", on_delete=models.CASCADE, related_name="inventory_movements"
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="inventory_movements",
    )
    pond_id = models.ForeignKey("ponds.Pond", on_delete=models.CASCADE, null=True)
    cycle_id = models.ForeignKey("cycle.Cycle", on_delete=models.CASCADE, null=True)
    movement_type = models.CharField(max_length=10, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observations = models.TextField(blank=True)
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, null=True, blank=True
    )
    source_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_movement"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["farm", "product"]),
            models.Index(fields=["source_type", "source_id"]),
        ]

    def __str__(self):
        return f"{self.movement_type} | {self.product} x{self.quantity}"
