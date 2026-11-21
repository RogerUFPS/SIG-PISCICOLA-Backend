from rest_framework import serializers

from .models import Alert, AuditLog, Unit


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = "__all__"


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user",
            "user_name",
            "farm_id",
            "description",
            "type_source",
            "source_id",
            "ip",
            "old_values",
            "new_values",
            "created_at",
        ]

    def get_user_name(self, obj) -> str | None:
        if obj.user is None:
            return None
        full_name = f"{obj.user.name or ''} {obj.user.lastname or ''}".strip()
        return full_name or obj.user.email


class AuditLogFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        error_messages={"invalid": "Formato de fecha inválido. Use YYYY-MM-DD."},
    )
    date_to = serializers.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        error_messages={"invalid": "Formato de fecha inválido. Use YYYY-MM-DD."},
    )
    origin = serializers.ChoiceField(
        required=False,
        choices=AuditLog.TypeSource.choices,
        error_messages={"invalid_choice": "El tipo de origen no es válido."},
    )
    origin_id = serializers.IntegerField(
        required=False,
        min_value=1,
        error_messages={
            "invalid": "El ID de origen debe ser un entero.",
            "min_value": "El ID de origen debe ser mayor que cero.",
        },
    )
    user = serializers.CharField(required=False, allow_blank=False, max_length=254)
    ip = serializers.IPAddressField(
        required=False,
        error_messages={"invalid": "La IP debe ser IPv4 o IPv6 válida."},
    )

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_to": "Debe ser igual o posterior a la fecha inicial."}
            )
        return attrs

    def validate_user(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "Ingresa un ID, nombre, apellido o correo."
            )
        return value


class AlertSerializer(serializers.ModelSerializer):
    resolved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        fields = [
            "id",
            "farm",
            "pond",
            "cycle",
            "source_type",
            "source_id",
            "description",
            "message",
            "value",
            "threshold",
            "severity",
            "is_resolved",
            "resolved_at",
            "resolved_by",
            "resolved_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_resolved_by_name(self, obj) -> str | None:
        if obj.resolved_by:
            return f"{obj.resolved_by.name} {obj.resolved_by.lastname}"
        return None
