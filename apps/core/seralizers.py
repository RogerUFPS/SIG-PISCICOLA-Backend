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
