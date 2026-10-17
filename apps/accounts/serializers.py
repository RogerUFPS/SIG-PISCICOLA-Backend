# serializers.py
from django.apps import apps
from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import serializers

from .models import Invitation, Role, RoleAppPermission, User


def get_role_permission_app_labels():
    return {
        app_config.label
        for app_config in apps.get_app_configs()
        if app_config.name.startswith("apps.") and app_config.label != "accounts"
    }


class RoleAppPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleAppPermission
        fields = ["app", "can_view", "can_create", "can_edit", "can_delete"]

    def validate_app(self, value):
        if value not in get_role_permission_app_labels():
            raise serializers.ValidationError("La aplicación no es válida.")
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


class RoleSerializer(serializers.ModelSerializer):
    app_permissions = RoleAppPermissionSerializer(many=True, required=False)

    class Meta:
        model = Role
        fields = ["id", "name", "app_permissions"]

    def validate_app_permissions(self, permissions):
        app_labels = [permission["app"] for permission in permissions]
        if len(app_labels) != len(set(app_labels)):
            raise serializers.ValidationError(
                "No se puede repetir una aplicación en los permisos del rol."
            )
        return permissions

    @transaction.atomic
    def create(self, validated_data):
        permissions = validated_data.pop("app_permissions", [])
        role = Role.objects.create(**validated_data)
        RoleAppPermission.objects.bulk_create(
            [RoleAppPermission(role=role, **permission) for permission in permissions]
        )
        return role

    @transaction.atomic
    def update(self, instance, validated_data):
        permissions = validated_data.pop("app_permissions", None)
        instance = super().update(instance, validated_data)
        if permissions is not None:
            instance.app_permissions.all().delete()
            RoleAppPermission.objects.bulk_create(
                [
                    RoleAppPermission(role=instance, **permission)
                    for permission in permissions
                ]
            )
        return instance


class CompleteProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["name", "lastname", "cc", "phone"]

    def validate_cc(self, value):
        user = self.context["request"].user
        if User.objects.filter(cc=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Ya existe un usario con esta cédula.")
        return value

    def update(self, instance, validated_data):
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.is_profile_complete = True
        instance.save()
        return instance


class InviteProductorSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Ya está registrado ese correo.")
        return value


class InviteOperarioSerializer(serializers.Serializer):
    email = serializers.EmailField()
    farm_id = serializers.IntegerField()

    def validate_farm_id(self, value):
        user = self.context["request"].user

        UserFarm = apps.get_model("farms", "UserFarm")

        if user.role.name == "Productor":
            owns_farm = UserFarm.objects.filter(
                user=user,
                farm_id=value,
                is_owner=True,
                status=UserFarm.Status.ACTIVE,
            ).exists()

            if not owns_farm:
                raise serializers.ValidationError(
                    "No tienes permisos sobre esta granja."
                )
        return value


class InvitationSerializer(serializers.ModelSerializer):
    invited_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = [
            "id",
            "farm_id",
            "email",
            "status",
            "invited_by",
            "invited_by_name",
            "user",
            "created_at",
        ]
        read_only_fields = ["status", "invited_by", "user", "created_at"]

    def get_invited_by_name(self, obj):
        if obj.invited_by:
            return f"{obj.invited_by.name} {obj.invited_by.lastname}"
        return None


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value

    def validate_new_password(self, value):
        if self.context["request"].user.check_password(value):
            raise serializers.ValidationError(
                "La nueva contraseña no puede ser igual a la actual."
            )
        return value

    def save(self):
        from .utils import change_user_password

        user = self.context["request"].user
        change_user_password(user, self.validated_data["new_password"])


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(
            request=self.context.get("request"),
            username=data["email"],
            password=data["password"],
        )
        if not user:
            raise serializers.ValidationError(
                "Credenciales inválidas o cuenta bloqueada."
            )
        data["user"] = user
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "lastname",
            "cc",
            "email",
            "phone",
            "role",
            "created_at",
        ]
        read_only_fields = ["cc", "email", "created_at"]


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ConfirmResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=8)


class OperarioSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "lastname",
            "cc",
            "email",
            "phone",
            "role",
            "created_at",
        ]


class ProductorSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    operarios = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "lastname",
            "cc",
            "email",
            "phone",
            "role",
            "created_at",
            "operarios",
        ]

    def get_operarios(self, productor):
        UserFarm = apps.get_model("farms", "UserFarm")

        farm_ids = UserFarm.objects.filter(
            user=productor,
            is_owner=True,
        ).values_list("farm_id", flat=True)

        operarios = User.objects.filter(
            user_farms__farm_id__in=farm_ids,
            role__name="Operario",
        ).select_related("role").distinct()

        return OperarioSerializer(operarios, many=True).data


class UserListSerializer(serializers.Serializer):
    admins = OperarioSerializer(many=True)
    productores = ProductorSerializer(many=True)
    operarios = OperarioSerializer(many=True)
