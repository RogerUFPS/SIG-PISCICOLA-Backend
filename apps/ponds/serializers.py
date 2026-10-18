# serializers.py

from decimal import Decimal

from django.apps import apps
from django.db.models import Sum
from rest_framework import serializers

from .models import Pond, UserFarmPond


def area_to_hectares(value):
    return Decimal(str(value)) / Decimal("10000")


class PondSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pond
        fields = [
            "id",
            "farm",
            "name",
            "code",
            "status",
            "type",
            "capacity",
            "area",
            "volume",
            "depth",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["farm", "created_at", "updated_at", "code"]

    def validate(self, data):
        farm = self.context["farm"]
        name = data.get("name", getattr(self.instance, "name", None))
        code = data.get("code", getattr(self.instance, "code", None))
        area = data.get("area", getattr(self.instance, "area", None))

        # Validar que no se pueda modificar un estanque inactivo (excepto el status)
        if self.instance and self.instance.status == Pond.Status.INACTIVE:
            # Permitir cambiar el status, pero no otros campos
            if any(key != "status" for key in data.keys()):
                raise serializers.ValidationError(
                    "No se puede modificar un estanque inactivo. Solo se puede cambiar su estado a activo."
                )

        qs_name = Pond.objects.filter(
            farm=farm, name__iexact=name, deleted_at__isnull=True
        )
        qs_code = Pond.objects.filter(
            farm=farm, code__iexact=code, deleted_at__isnull=True
        )

        if self.instance:
            qs_name = qs_name.exclude(pk=self.instance.pk)
            qs_code = qs_code.exclude(pk=self.instance.pk)

        if qs_name.exists():
            raise serializers.ValidationError(
                {"name": "Ya existe un estanque con este nombre en la granja."}
            )
        if qs_code.exists():
            raise serializers.ValidationError(
                {"code": "Ya existe un estanque con este código en la granja."}
            )

        if area is not None:
            farm_total_area_ha = Decimal(str(farm.total_area_ha))

            current_total = sum(
                (
                    area_to_hectares(value)
                    for value in Pond.objects.filter(
                        farm=farm, deleted_at__isnull=True
                    )
                    .exclude(pk=getattr(self.instance, "pk", None))
                    .values_list("area", flat=True)
                ),
                Decimal("0"),
            )
            total_area = current_total + area_to_hectares(area)

            if total_area > farm_total_area_ha:
                raise serializers.ValidationError(
                    "El área total de los estanques supera el área total de la granja."
                )

        return data


class UserFarmPondSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = UserFarmPond
        fields = ["id", "user", "farm", "pond", "user_name", "user_email"]
        read_only_fields = ["farm", "pond"]

    def get_user_name(self, obj):
        return f"{obj.user.name} {obj.user.lastname}"

    def get_user_email(self, obj):
        return obj.user.email

    def validate_user(self, user):
        farm = self.context["farm"]
        pond = self.context["pond"]

        if user.role.name != "Operario":
            raise serializers.ValidationError(
                "Solo se pueden asignar Operarios a un estanque."
            )

        UserFarm = apps.get_model("farms", "UserFarm")

        in_farm = UserFarm.objects.filter(
            user=user,
            farm=farm,
            status=UserFarm.Status.ACTIVE,
        ).exists()
        if not in_farm:
            raise serializers.ValidationError("El operario no pertenece a esta granja.")

        already = UserFarmPond.objects.filter(user=user, farm=farm, pond=pond).exists()
        if already:
            raise serializers.ValidationError(
                "El operario ya está asignado a este estanque."
            )

        return user
