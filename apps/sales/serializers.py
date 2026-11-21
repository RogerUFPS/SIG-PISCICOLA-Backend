import re

from rest_framework import serializers

from .models import Client, Sale, SaleDetail
from .utils import get_classification_available_fish_count_for_sale

_DOCUMENT_RULES: dict[str, tuple[str, str]] = {
    Client.DocumentType.CC: (
        r"^\d{6,10}$",
        "La CC debe contener entre 6 y 10 dígitos numéricos.",
    ),
    Client.DocumentType.CE: (
        r"^[A-Za-z0-9]{4,12}$",
        "La CE debe ser alfanumérica (4–12 caracteres).",
    ),
    Client.DocumentType.NIT: (
        r"^\d{9,10}(-\d)?$",
        "El NIT debe tener 9–10 dígitos, con dígito de verificación opcional (ej. 900123456-7).",
    ),
    Client.DocumentType.PAS: (
        r"^[A-Za-z0-9]{5,15}$",
        "El pasaporte debe ser alfanumérico (5–15 caracteres).",
    ),
    Client.DocumentType.PPT: (
        r"^[A-Za-z0-9]{6,20}$",
        "El PPT debe ser alfanumérico (6–20 caracteres).",
    ),
}


def _validate_document_format(document_type: str, document_number: str) -> None:
    rule = _DOCUMENT_RULES.get(document_type)
    if rule is None:
        return
    pattern, message = rule
    if not re.match(pattern, document_number):
        raise serializers.ValidationError({"document_number": message})


def _validate_client_type_document_type(
    client_type: str,
    document_type: str,
) -> None:
    if (
        client_type == Client.ClientType.JURIDICO
        and document_type != Client.DocumentType.NIT
    ):
        raise serializers.ValidationError(
            {
                "document_type": "Los clientes jurídicos solo pueden usar NIT como tipo de documento."
            }
        )
    if (
        client_type == Client.ClientType.NATURAL
        and document_type == Client.DocumentType.NIT
    ):
        raise serializers.ValidationError(
            {
                "document_type": "Los clientes naturales no pueden usar NIT como tipo de documento."
            }
        )


class ClientCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "client_type",
            "name",
            "document_type",
            "document_number",
            "phone",
            "email",
            "address",
            "observations",
        ]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                "El nombre debe tener al menos 2 caracteres."
            )
        return value

    def validate_document_number(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "El número de documento no puede estar vacío."
            )
        return value

    def validate_phone(self, value: str) -> str:
        if value and not re.match(r"^\+?[\d\s\-\(\)]{7,20}$", value):
            raise serializers.ValidationError(
                "Formato de teléfono inválido. Use solo dígitos, espacios, guiones o paréntesis."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        client_type = attrs["client_type"]
        document_type = attrs["document_type"]
        document_number = attrs["document_number"]
        farm = self.context["farm"]

        _validate_client_type_document_type(client_type, document_type)
        _validate_document_format(document_type, document_number)

        qs = Client.objects.filter(
            farm=farm,
            document_type=document_type,
            document_number=document_number,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "document_number": (
                        "Ya existe un cliente con este tipo y número de documento "
                        "registrado en esta finca."
                    )
                }
            )
        return attrs


class ClientListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "id",
            "farm",
            "client_type",
            "name",
            "document_type",
            "document_number",
            "phone",
            "email",
        ]
        read_only_fields = fields


class ClientDetailSerializer(serializers.ModelSerializer):
    client_type_display = serializers.CharField(
        source="get_client_type_display", read_only=True
    )
    document_type_display = serializers.CharField(
        source="get_document_type_display", read_only=True
    )

    class Meta:
        model = Client
        fields = [
            "id",
            "farm",
            "client_type",
            "client_type_display",
            "name",
            "document_type",
            "document_type_display",
            "document_number",
            "phone",
            "email",
            "address",
            "observations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ClientUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "client_type",
            "name",
            "document_type",
            "document_number",
            "phone",
            "email",
            "address",
            "observations",
        ]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError(
                "El nombre debe tener al menos 2 caracteres."
            )
        return value

    def validate_document_number(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "El número de documento no puede estar vacío."
            )
        return value

    def validate_phone(self, value: str) -> str:
        if value and not re.match(r"^\+?[\d\s\-\(\)]{7,20}$", value):
            raise serializers.ValidationError(
                "Formato de teléfono inválido. Use solo dígitos, espacios, guiones o paréntesis."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        client_type = attrs.get("client_type", self.instance.client_type)
        document_type = attrs.get("document_type", self.instance.document_type)
        document_number = attrs.get("document_number", self.instance.document_number)

        _validate_client_type_document_type(client_type, document_type)
        _validate_document_format(document_type, document_number)

        qs = Client.objects.filter(
            farm=self.instance.farm,
            document_type=document_type,
            document_number=document_number,
        ).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "document_number": (
                        "Ya existe un cliente con este tipo y número de documento "
                        "registrado en esta finca."
                    )
                }
            )
        return attrs


class SaleCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sale
        fields = [
            "client",
            "invoice_number",
            "payment_method",
            "observations",
            "date",
            "created_by",
        ]
        extra_kwargs = {
            "created_by": {"read_only": True},
            "date": {"required": False},
        }

    def validate_invoice_number(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "El número de factura no puede estar vacío."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        farm = self.context["farm"]
        invoice_number = attrs["invoice_number"]
        client = attrs.get("client")

        qs = Sale.objects.filter(farm=farm, invoice_number=invoice_number)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "invoice_number": "Ya existe una venta con este número de factura en esta finca."
                }
            )
        if client is not None and client.farm_id != farm.pk:
            raise serializers.ValidationError(
                {"client": "El cliente seleccionado no pertenece a la finca indicada."}
            )
        return attrs


class SaleListSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(
        source="client.name", read_only=True, default=None
    )
    payment_method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )

    class Meta:
        model = Sale
        fields = [
            "id",
            "farm",
            "client",
            "client_name",
            "invoice_number",
            "payment_method",
            "payment_method_display",
            "date",
            "total",
            "created_by",
        ]
        read_only_fields = fields


class _SaleItemInlineSerializer(serializers.ModelSerializer):
    """Read-only nested serializer para detalles dentro de una venta."""

    harvest_classification_name = serializers.CharField(
        source="harvest_classification.name", read_only=True
    )
    # ✅ subtotal ahora es simplemente el price (total del detalle)
    subtotal = serializers.DecimalField(
        source="price", max_digits=16, decimal_places=2, read_only=True
    )

    class Meta:
        model = SaleDetail
        fields = [
            "id",
            "harvest_classification",
            "harvest_classification_name",
            "quantity_g",
            "fish_count",
            "price",
            "subtotal",
        ]
        read_only_fields = fields


class SaleDetailSerializer(serializers.ModelSerializer):
    """Detalle completo de una venta (cabecera + líneas)."""

    client_name = serializers.CharField(
        source="client.name", read_only=True, default=None
    )
    payment_method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
    created_by_username = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )
    items = _SaleItemInlineSerializer(source="details", many=True, read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "farm",
            "client",
            "client_name",
            "invoice_number",
            "payment_method",
            "payment_method_display",
            "observations",
            "date",
            "created_by",
            "created_by_username",
            "items",
            "total",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SaleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sale
        fields = [
            "client",
            "invoice_number",
            "payment_method",
            "observations",
            "date",
        ]

    def validate_invoice_number(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "El número de factura no puede estar vacío."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        invoice_number = attrs.get("invoice_number", self.instance.invoice_number)
        client = attrs.get("client", self.instance.client)

        qs = Sale.objects.filter(
            farm=self.instance.farm,
            invoice_number=invoice_number,
        ).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "invoice_number": "Ya existe una venta con este número de factura en esta finca."
                }
            )
        if client is not None and client.farm_id != self.instance.farm_id:
            raise serializers.ValidationError(
                {
                    "client": "El cliente seleccionado no pertenece a la finca de esta venta."
                }
            )
        return attrs


class SaleDetailCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleDetail
        fields = [
            "farm",
            "sale",
            "harvest_classification",
            "quantity_g",
            "fish_count",
            "price",
        ]

    def validate_quantity_g(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a cero.")
        return value

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio total no puede ser negativo.")
        return value

    def validate_fish_count(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                "La cantidad de peces debe ser mayor a cero."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        farm = attrs["farm"]
        sale = attrs["sale"]
        harvest_classification = attrs["harvest_classification"]
        fish_count = attrs.get("fish_count")

        if sale.farm_id != farm.pk:
            raise serializers.ValidationError(
                {"farm": "La finca indicada no coincide con la finca de la venta."}
            )

        qs = SaleDetail.objects.filter(
            sale=sale,
            harvest_classification=harvest_classification,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "harvest_classification": (
                        "Esta clasificación de cosecha ya está registrada en la venta. "
                        "Edite el detalle existente en lugar de crear uno nuevo."
                    )
                }
            )

        if fish_count is not None:
            exclude_id = self.instance.pk if self.instance else None
            available_fish = get_classification_available_fish_count_for_sale(
                harvest_classification, exclude_detail_id=exclude_id
            )
            if fish_count > available_fish:
                raise serializers.ValidationError(
                    {
                        "fish_count": (
                            f"Cantidad de peces solicitada ({fish_count}) supera la disponible "
                            f"({available_fish}) para la clasificación '{harvest_classification}'."
                        )
                    }
                )
        return attrs


class SaleDetailListSerializer(serializers.ModelSerializer):
    harvest_classification_name = serializers.CharField(
        source="harvest_classification.name", read_only=True
    )
    subtotal = serializers.DecimalField(
        source="price", max_digits=16, decimal_places=2, read_only=True
    )
    sale_observations = serializers.CharField(
        source="sale.observations", read_only=True
    )
    invoice_number = serializers.CharField(source="sale.invoice_number", read_only=True)
    sale_date = serializers.DateField(source="sale.date", read_only=True)

    class Meta:
        model = SaleDetail
        fields = [
            "id",
            "sale",
            "invoice_number",
            "sale_date",
            "sale_observations",
            "harvest_classification",
            "harvest_classification_name",
            "quantity_g",
            "fish_count",
            "price",
            "subtotal",
        ]
        read_only_fields = fields


class SaleDetailByHarvestSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="sale.invoice_number", read_only=True)
    sale_date = serializers.DateField(source="sale.date", read_only=True)
    payment_method = serializers.CharField(source="sale.payment_method", read_only=True)
    payment_method_display = serializers.CharField(
        source="sale.get_payment_method_display", read_only=True
    )
    client_name = serializers.CharField(
        source="sale.client.name", read_only=True, default=None
    )
    subtotal = serializers.DecimalField(
        source="price", max_digits=16, decimal_places=2, read_only=True
    )

    class Meta:
        model = SaleDetail
        fields = [
            "id",
            "harvest_classification",
            "sale",
            "invoice_number",
            "sale_date",
            "payment_method",
            "payment_method_display",
            "client_name",
            "quantity_g",
            "fish_count",
            "price",
            "subtotal",
        ]
        read_only_fields = fields


class SaleDetailUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleDetail
        fields = [
            "harvest_classification",
            "quantity_g",
            "fish_count",
            "price",
        ]

    def validate_quantity_g(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor a cero.")
        return value

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio total no puede ser negativo.")
        return value

    def validate_fish_count(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                "La cantidad de peces debe ser mayor a cero."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        harvest_classification = attrs.get(
            "harvest_classification", self.instance.harvest_classification
        )

        qs = SaleDetail.objects.filter(
            sale=self.instance.sale,
            harvest_classification=harvest_classification,
        ).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {
                    "harvest_classification": (
                        "Esta clasificación de cosecha ya está registrada en la venta."
                    )
                }
            )

        if "fish_count" in attrs and attrs["fish_count"] is not None:
            available_fish = get_classification_available_fish_count_for_sale(
                harvest_classification,
                exclude_detail_id=self.instance.pk,
            )
            if attrs["fish_count"] > available_fish:
                raise serializers.ValidationError(
                    {
                        "fish_count": (
                            f"Cantidad de peces solicitada ({attrs['fish_count']}) supera la disponible "
                            f"({available_fish}) para la clasificación '{harvest_classification}'."
                        )
                    }
                )
        return attrs
