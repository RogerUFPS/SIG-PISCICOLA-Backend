# serializers.py
from django.db import transaction
from rest_framework import serializers

from .models import Buy, InventoryMovement, PurchaseDetail
from .utils import (_create_inventory_movement, _delete_details_with_movements,
                    _maybe_create_batch_from_purchase)


class BatchDataSerializer(serializers.Serializer):
    specie_id = serializers.IntegerField()
    biological_state = serializers.CharField(required=False, default="alevin")
    min_weight_g = serializers.FloatField()
    avg_weight_g = serializers.FloatField()
    max_weight_g = serializers.FloatField()
    comments = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if not (data["min_weight_g"] <= data["avg_weight_g"] <= data["max_weight_g"]):
            raise serializers.ValidationError(
                "min_weight_g <= avg_weight_g <= max_weight_g debe cumplirse."
            )
        return data


class PurchaseDetailSerializer(serializers.ModelSerializer):
    batch_data = BatchDataSerializer(required=False, write_only=True)

    class Meta:
        model = PurchaseDetail
        fields = [
            "id",
            "product",
            "unit",
            "quantity",
            "unit_value",
            "total_value",
            "batch_data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["unit", "total_value", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs["total_value"] = attrs["quantity"] * attrs["unit_value"]

        product = attrs.get("product")
        if product and product.type_product.name.lower() == "lote":
            if "batch_data" not in attrs:
                raise serializers.ValidationError(
                    {
                        "batch_data": "Este producto es de tipo 'Lote'. Debes enviar batch_data."
                    }
                )
        return attrs


class BuySerializer(serializers.ModelSerializer):
    details = PurchaseDetailSerializer(many=True)

    class Meta:
        model = Buy
        fields = [
            "id",
            "farm",
            "supplier",
            "date",
            "invoice_number",
            "comments",
            "details",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["farm", "created_at", "updated_at"]

    def validate_details(self, value):
        if not value:
            raise serializers.ValidationError(
                "Una compra debe tener al menos un detalle."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        details_data = validated_data.pop("details")
        buy = Buy.objects.create(**validated_data)

        for detail_data in details_data:
            batch_data = detail_data.pop("batch_data", None)
            detail_data["unit"] = detail_data["product"].unit
            detail = PurchaseDetail.objects.create(buy=buy, **detail_data)
            _create_inventory_movement(buy, detail)
            if batch_data:
                _maybe_create_batch_from_purchase(detail, batch_data)

        return buy

    @transaction.atomic
    def update(self, instance, validated_data):
        details_data = validated_data.pop("details", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if details_data is not None:
            _delete_details_with_movements(instance)
            for detail_data in details_data:
                batch_data = detail_data.pop("batch_data", None)
                detail_data["unit"] = detail_data["product"].unit
                detail = PurchaseDetail.objects.create(buy=instance, **detail_data)
                _create_inventory_movement(instance, detail)
                if batch_data:
                    _maybe_create_batch_from_purchase(detail, batch_data)

        return instance


class InventoryMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryMovement
        fields = [
            "id",
            "farm",
            "product",
            "pond_id",
            "cycle_id",
            "movement_type",
            "quantity",
            "unit_cost",
            "total_cost",
            "observations",
            "source_type",
            "source_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
