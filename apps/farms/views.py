from django.utils import timezone
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.permissions import AdminOr, IsProductor

from .enums import FarmPermission
from .models import City, Department, Farm, FarmRole, UserFarm
from .permissions import (CanManageFarm, CanManageFarmUsers, IsFarmMember,
                          IsFarmOwner, user_may_access_farm)
from .serializers import (CitySerializer, DepartmentSerializer,
                          FarmRoleSerializer, FarmSerializer,
                          UserFarmSerializer)
from .utils import (
    assign_operario_permissions,
    assign_role_to_operario,
    farm_has_active_resources,
)


class DepartmentListView(generics.ListAPIView):
    serializer_class = DepartmentSerializer
    permission_classes = [AllowAny]
    queryset = Department.objects.order_by("name")


class CityListView(generics.ListAPIView):
    serializer_class = CitySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = City.objects.select_related("department").order_by("name")
        department_id = self.request.query_params.get("department_id")
        if department_id:
            qs = qs.filter(department_id=department_id)
        return qs


class FarmViewSet(viewsets.ModelViewSet):
    serializer_class = FarmSerializer

    @staticmethod
    def _base_queryset():
        return Farm.objects.filter(deleted_at__isnull=True).select_related(
            "department", "city"
        )

    def get_permissions(self):
        if self.action == "create":
            perms = [AdminOr(IsProductor)]
        elif self.action in ("update", "partial_update"):
            perms = [AdminOr(CanManageFarm)]
        elif self.action == "destroy":
            perms = [AdminOr(IsFarmOwner)]
        else:
            perms = [AdminOr(IsFarmMember)]
        return [p() for p in perms]

    def get_queryset(self):
        user = self.request.user
        queryset = self._base_queryset().order_by("-id")

        if user.role.name == "Admin":
            productor_id = self.request.query_params.get("productor_id")
            if productor_id:
                queryset = queryset.filter(
                    user_farms__user_id=productor_id,
                    user_farms__is_owner=True,
                )
            return queryset.distinct()

        return queryset.filter(user_farms__user=user)

    def perform_create(self, serializer):
        productor = serializer.validated_data.pop("_productor", None)
        farm = serializer.save()
        owner = productor if productor else self.request.user
        UserFarm.objects.create(
            user=owner,
            farm=farm,
            permissions=int(FarmPermission.ALL),
            is_owner=True,
            status=UserFarm.Status.ACTIVE,
        )

    def destroy(self, request, *args, **kwargs):
        farm = self.get_object()

        if farm_has_active_resources(farm):
            return Response(
                {
                    "detail": (
                        "No se puede eliminar la granja porque tiene ciclos o "
                        "estanques activos. Finalice los ciclos e inactive los "
                        "estanques primero."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        farm.deleted_at = timezone.now()
        farm.save(update_fields=["deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False, methods=["get"], url_path="productor/(?P<productor_id>[^/.]+)"
    )
    def by_productor(self, request, productor_id=None):
        if request.user.role.name != "Admin":
            return Response(
                {"detail": "No tienes permiso para realizar esta acción."},
                status=status.HTTP_403_FORBIDDEN,
            )
        farms = (
            self._base_queryset()
            .filter(user_farms__user_id=productor_id, user_farms__is_owner=True)
            .distinct()
            .order_by("-id")
        )
        return Response(self.get_serializer(farms, many=True).data)


class FarmRoleViewSet(viewsets.ModelViewSet):
    serializer_class = FarmRoleSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            perms = [AdminOr(CanManageFarmUsers)]
        else:
            perms = [AdminOr(IsFarmMember)]
        return [p() for p in perms]

    def get_queryset(self):
        farm_pk = self.kwargs["farm_pk"]
        qs = FarmRole.objects.filter(
            farm_id=farm_pk,
            farm__deleted_at__isnull=True,
            deleted_at__isnull=True,
        )
        if not user_may_access_farm(self.request.user, farm_pk):
            return qs.none()
        return qs.order_by("name")

    def perform_create(self, serializer):
        serializer.save(farm_id=self.kwargs["farm_pk"])

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        role.deleted_at = timezone.now()
        role.save(update_fields=["deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserFarmViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = UserFarmSerializer
    lookup_field = "user_id"
    lookup_url_kwarg = "user_id"

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy"):
            perms = [AdminOr(CanManageFarmUsers)]
        else:
            perms = [AdminOr(IsFarmMember)]
        return [p() for p in perms]

    def get_queryset(self):
        farm_pk = self.kwargs["farm_pk"]
        qs = UserFarm.objects.filter(
            farm_id=farm_pk,
            farm__deleted_at__isnull=True,
        )
        if not user_may_access_farm(self.request.user, farm_pk):
            return qs.none()
        return qs.select_related("user", "farm_role").order_by("user__id")

    def update(self, request, *args, **kwargs):
        member = self.get_object()

        if member.user.role.name == "Operario":
            farm_role_id = request.data.get("farm_role")
            if farm_role_id:
                try:
                    role = FarmRole.objects.get(
                        pk=farm_role_id,
                        farm_id=member.farm_id,
                        deleted_at__isnull=True,
                    )
                except FarmRole.DoesNotExist:
                    return Response(
                        {"farm_role": "Rol no encontrado en esta finca."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                try:
                    assign_role_to_operario(member, role)
                except ValueError as e:
                    return Response(
                        {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST
                    )

            if "permissions" in request.data:
                try:
                    assign_operario_permissions(member, request.data["permissions"])
                except ValueError as e:
                    return Response(
                        {"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST
                    )

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        member = self.get_object()
        if member.is_owner:
            return Response(
                {"detail": "No se puede eliminar al propietario de la finca."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
