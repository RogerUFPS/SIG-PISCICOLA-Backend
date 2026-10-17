from django.apps import apps
from django.db import transaction
from rest_framework import serializers

from .enums import FarmPermission
from .models import City, Department, Farm, FarmRole, FarmRoleAppPermission, UserFarm


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


class PermissionsField(serializers.Field):
    def to_representation(self, value: int) -> list[str]:
        return [
            p.name for p in FarmPermission if p != FarmPermission.ALL and (value & p)
        ]

    def to_internal_value(self, data) -> int:
        if not isinstance(data, list):
            raise serializers.ValidationError("Se esperaba una lista de permisos.")

        result = 0
        valid_names = {p.name for p in FarmPermission if p != FarmPermission.ALL}

        for name in data:
            if name not in valid_names:
                raise serializers.ValidationError(
                    f"Permiso inválido: '{name}'. Opciones: {sorted(valid_names)}"
                )
            result |= FarmPermission[name]

        return int(result)


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


def get_role_permission_apps():
    return {
        config.label: config.verbose_name
        for config in apps.get_app_configs()
        if config.name.startswith("apps.") and config.label != "accounts"
    }


class FarmRoleAppPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FarmRoleAppPermission
        fields = ["app", "can_view", "can_create", "can_edit", "can_delete"]

    def validate_app(self, value):
        if value not in get_role_permission_apps():
            raise serializers.ValidationError("La aplicación no está implementada.")
        return value

    def validate(self, attrs):
        if any(
            attrs.get(field, getattr(self.instance, field, False))
            for field in ("can_create", "can_edit", "can_delete")
        ) and not attrs.get("can_view", getattr(self.instance, "can_view", False)):
            raise serializers.ValidationError(
                {"can_view": "El permiso de ver es obligatorio para los demás permisos."}
            )
        return attrs


class FarmRoleSerializer(serializers.ModelSerializer):
    permissions = PermissionsField(required=False, default=0)
    app_permissions = FarmRoleAppPermissionSerializer(many=True, required=False)

    class Meta:
        model = FarmRole
        fields = ["id", "farm", "name", "permissions", "app_permissions"]
        read_only_fields = ["farm"]

    def validate_app_permissions(self, permissions):
        app_names = [permission["app"] for permission in permissions]
        if len(app_names) != len(set(app_names)):
            raise serializers.ValidationError(
                "No se puede repetir una aplicación en los permisos del rol."
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
        app_permissions = validated_data.pop("app_permissions", [])
        role = FarmRole.objects.create(
            permissions_configured=True,
            **validated_data,
        )
        FarmRoleAppPermission.objects.bulk_create(
            [
                FarmRoleAppPermission(role=role, **permission)
                for permission in app_permissions
            ]
        )
        return role

    @transaction.atomic
    def update(self, instance, validated_data):
        app_permissions = validated_data.pop("app_permissions", None)
        instance = super().update(instance, validated_data)
        if app_permissions is not None:
            instance.permissions_configured = True
            instance.save(update_fields=["permissions_configured"])
            instance.app_permissions.all().delete()
            FarmRoleAppPermission.objects.bulk_create(
                [
                    FarmRoleAppPermission(role=instance, **permission)
                    for permission in app_permissions
                ]
            )
        return instance


class UserFarmSerializer(serializers.ModelSerializer):
    permissions = PermissionsField(required=False, default=0)
    user = UserSummarySerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=apps.get_model("accounts", "User").objects.all(),
        source="user",
        write_only=True,
    )

    class Meta:
        model = UserFarm
        fields = [
            "user",
            "user_id",
            "farm",
            "farm_role",
            "permissions",
            "status",
            "is_owner",
        ]

    def validate(self, attrs):
        farm = attrs.get("farm", getattr(self.instance, "farm", None))
        farm_role = attrs.get("farm_role", getattr(self.instance, "farm_role", None))
        user = attrs.get("user", getattr(self.instance, "user", None))
        is_owner = attrs.get("is_owner", getattr(self.instance, "is_owner", False))

        if farm_role and farm_role.farm_id != farm.id:
            raise serializers.ValidationError(
                {"farm_role": "El rol no pertenece a esta finca."}
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
