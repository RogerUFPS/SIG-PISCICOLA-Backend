import re

from rest_framework import serializers

from .models import Product, Supplier, TypeProduct


class TypeProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeProduct
        fields = ["id", "name"]


class ProductSerializer(serializers.ModelSerializer):
    type_product_name = serializers.CharField(
        source="type_product.name", read_only=True
    )
    unit_symbol = serializers.CharField(source="core.unit.symbol", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "type_product",
            "type_product_name",
            "farm",
            "unit",
            "unit_symbol",
            "name",
            "comments",
            "minimun_stock_threshold",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["farm", "created_at", "updated_at"]

    def validate_name(self, value):
        farm_id = self.context["view"].kwargs.get("farm_pk")
        qs = Product.objects.filter(
            name__iexact=value,
            farm_id=farm_id,
            deleted_at__isnull=True,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya existe un producto con este nombre en la finca."
            )
        return value


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id",
            "farm",
            "supplier_type",
            "name",
            "document_type",
            "document_number",
            "phone",
            "email",
            "address",
            "observations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["farm", "created_at", "updated_at"]

    def validate_phone(self, value):
        if value and not re.fullmatch(r"[0-9]{10}", value):
            raise serializers.ValidationError(
                "El teléfono del proveedor debe contener exactamente 10 dígitos."
            )
        return value

    def validate(self, attrs):
        farm_id = self.context["view"].kwargs.get("farm_pk")
        document_type = attrs.get(
            "document_type", getattr(self.instance, "document_type", None)
        )
        document_number = attrs.get(
            "document_number", getattr(self.instance, "document_number", None)
        )

        qs = Supplier.objects.filter(
            farm_id=farm_id,
            document_type=document_type,
            document_number=document_number,
            deleted_at__isnull=True,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "document_number": "Ya existe un proveedor con ese documento en esta finca."
                }
            )
        return attrs
