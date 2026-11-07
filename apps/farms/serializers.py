from django.apps import apps
from django.db import transaction
from rest_framework import serializers

from apps.core.signals import audit_bulk_create, audit_queryset_update

from .models import (
    City,
    Department,
    Farm,
    FarmRole,
    FarmRoleAppPermission,
    UserFarm,
    UserFarmPermission,
)
from .modules import MODULES, OPERATIONS


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = apps.get_model("accounts", "User")
        fields = ["id", "name", "lastname", "cc", "email", "phone"]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name"]


class CitySerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)

    class Meta:
        model = City
        fields = ["id", "name", "department"]


class FarmSerializer(serializers.ModelSerializer):
    productor_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Farm
        fields = [
            "id",
            "name",
            "department",
            "city",
            "address",
            "total_area_ha",
            "water_source",
            "status",
            "productor_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, data):
        user = self.context["request"].user

        if self.instance is not None or user.role.name != "Admin":
            return data

        if "productor_id" not in data:
            raise serializers.ValidationError(
                {
                    "productor_id": "Un Admin debe asignar un Productor al crear una granja."
                }
            )

        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            productor = User.objects.get(
                pk=data["productor_id"], role__name="Productor"
            )
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"productor_id": "No existe un Productor con ese ID."}
            )
        data["_productor"] = productor
        return data

    def validate_name(self, value):
        user = self.context["request"].user
        qs = Farm.objects.filter(
            user_farms__user=user,
            user_farms__is_owner=True,
            name__iexact=value,
            deleted_at__isnull=True,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ya eres propietario de una finca con este nombre."
            )
        return value


def get_role_permission_modules():
    return MODULES


class FarmRoleAppPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FarmRoleAppPermission
        fields = ["module", "can_view", "can_create", "can_update", "can_delete"]

    def to_internal_value(self, data):
        allowed = set(self.fields)
        if not hasattr(data, "keys") or set(data.keys()) - allowed:
            raise serializers.ValidationError(
                {
                    "non_field_errors": (
                        "Envía solo el módulo y las operaciones view, create, "
                        "update y delete."
                    )
                }
            )
        return super().to_internal_value(data)

    def validate_module(self, value):
        if value not in get_role_permission_modules():
            raise serializers.ValidationError("El módulo no está implementado.")
        return value

    def validate(self, attrs):
        module = attrs.get("module", getattr(self.instance, "module", None))
        if module in ("alerts", "audit_logs"):
            if any(
                attrs.get(f"can_{operation}", getattr(self.instance, f"can_{operation}", False))
                for operation in ("create", "update", "delete")
            ):
                raise serializers.ValidationError(
                    "Alertas y Audit logs solo permiten la operación view."
                )
        return attrs


class FarmRoleSerializer(serializers.ModelSerializer):
    module_permissions = FarmRoleAppPermissionSerializer(many=True, required=False)

    class Meta:
        model = FarmRole
        fields = ["id", "farm", "name", "module_permissions"]
        read_only_fields = ["farm"]

    def to_internal_value(self, data):
        if not hasattr(data, "keys") or set(data.keys()) - {
            "name",
            "module_permissions",
        }:
            raise serializers.ValidationError(
                {"non_field_errors": "Envía solo name y module_permissions."}
            )
        return super().to_internal_value(data)

    def validate_module_permissions(self, permissions):
        module_names = [permission["module"] for permission in permissions]
        if len(module_names) != len(set(module_names)):
            raise serializers.ValidationError(
                "No se puede repetir un módulo en los permisos del rol."
            )
        return permissions

    def validate(self, attrs):
        view = self.context.get("view")
        farm_id = getattr(self.instance, "farm_id", None)
        if farm_id is None and view is not None:
            farm_id = view.kwargs.get("farm_pk")
        qs = FarmRole.objects.filter(
            farm_id=farm_id,
            name__iexact=attrs.get("name", getattr(self.instance, "name", "")),
            deleted_at__isnull=True,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"name": "Ya existe un rol con este nombre en la finca."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        module_permissions = validated_data.pop("module_permissions", [])
        role = FarmRole.objects.create(**validated_data)
        if module_permissions:
            audit_bulk_create(
                FarmRoleAppPermission,
                [
                    FarmRoleAppPermission(role=role, **permission)
                    for permission in module_permissions
                ]
            )
        return role

    @transaction.atomic
    def update(self, instance, validated_data):
        module_permissions = validated_data.pop("module_permissions", None)
        instance = super().update(instance, validated_data)
        if module_permissions is not None:
            instance.module_permissions.all().delete()
            audit_bulk_create(
                FarmRoleAppPermission,
                [
                    FarmRoleAppPermission(role=instance, **permission)
                    for permission in module_permissions
                ]
            )
        return instance


class UserFarmPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserFarmPermission
        fields = ["id", "module", "operation"]
        read_only_fields = ["id"]

    def to_internal_value(self, data):
        if not hasattr(data, "keys") or set(data.keys()) != {"module", "operation"}:
            raise serializers.ValidationError(
                {"non_field_errors": "Envía exactamente un module y una operation."}
            )
        return super().to_internal_value(data)

    def validate_module(self, value):
        if value not in MODULES:
            raise serializers.ValidationError("El módulo no está implementado.")
        return value

    def validate_operation(self, value):
        if value not in OPERATIONS:
            raise serializers.ValidationError(
                f"Operación inválida. Opciones: {', '.join(OPERATIONS)}."
            )
        return value

    def validate(self, attrs):
        if attrs["module"] in ("alerts", "audit_logs") and attrs["operation"] != "view":
            raise serializers.ValidationError(
                {"operation": "Este módulo solo permite la operación view."}
            )
        return attrs


class UserFarmSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    personal_permissions = UserFarmPermissionSerializer(many=True, read_only=True)
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = UserFarm
        fields = [
            "user",
            "user_id",
            "farm",
            "farm_role",
            "personal_permissions",
            "effective_permissions",
            "status",
            "is_owner",
        ]
        read_only_fields = ["user", "user_id", "farm", "is_owner"]

    def get_effective_permissions(self, membership):
        from .utils import get_effective_permissions

        return get_effective_permissions(membership)

    def validate(self, attrs):
        farm = attrs.get("farm", getattr(self.instance, "farm", None))
        farm_role = attrs.get("farm_role", getattr(self.instance, "farm_role", None))
        user = attrs.get("user", getattr(self.instance, "user", None))
        is_owner = getattr(self.instance, "is_owner", False)

        if farm_role and farm_role.farm_id != farm.id:
            raise serializers.ValidationError(
                {"farm_role": "El rol no pertenece a esta finca."}
            )
        if farm_role and farm_role.deleted_at is not None:
            raise serializers.ValidationError(
                {"farm_role": "No se puede asignar un rol inactivo."}
            )

        if is_owner:
            qs = Farm.objects.filter(
                user_farms__user=user,
                user_farms__is_owner=True,
                name__iexact=farm.name if farm else "",
                deleted_at__isnull=True,
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.farm_id)
            if qs.exists():
                raise serializers.ValidationError(
                    {
                        "farm": "Este usuario ya es propietario de una finca con ese nombre."
                    }
                )

        return attrs
