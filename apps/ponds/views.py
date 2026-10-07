from django.apps import apps
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import AdminOr
from apps.farms.permissions import (CanManageFarmUsers, CanManagePond,
                                    IsFarmMember)

from .models import Pond, UserFarmPond
from .serializers import PondSerializer, UserFarmPondSerializer
from .utils import (
    get_pond_or_404,
    pond_has_cycles,
    remove_pond_member,
    soft_delete_pond,
)


def _get_farm(farm_id):
    Farm = apps.get_model("farms", "Farm")
    try:
        return Farm.objects.get(pk=farm_id, deleted_at__isnull=True)
    except Farm.DoesNotExist:
        return None


def _farm_not_found_response():
    return Response(
        {"detail": "Granja no encontrada."}, status=status.HTTP_404_NOT_FOUND
    )


def _pond_not_found_response():
    return Response(
        {"detail": "Estanque no encontrado."}, status=status.HTTP_404_NOT_FOUND
    )


def _pond_forbidden_for_operario_response():
    return Response(
        {"detail": "No tienes permiso para acceder a este estanque."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _filter_ponds_for_operario(qs, request, farm):
    if request.user.role.name == "Operario":
        pond_ids = UserFarmPond.objects.filter(
            user=request.user,
            farm=farm,
        ).values_list("pond_id", flat=True)
        qs = qs.filter(id__in=pond_ids)
    return qs


class PondListCreateView(APIView):

    def get_permissions(self):
        if self.request.method == "POST":
            return [AdminOr(CanManagePond)()]
        return [AdminOr(IsFarmMember)()]

    def get(self, request, farm_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        qs = Pond.objects.filter(farm=farm, deleted_at__isnull=True).order_by("-id")
        qs = _filter_ponds_for_operario(qs, request, farm)

        return Response(PondSerializer(qs, many=True).data)

    def post(self, request, farm_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        serializer = PondSerializer(
            data=request.data,
            context={"request": request, "farm": farm},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(farm=farm)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PondAllowedListView(APIView):

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    def get(self, request, farm_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        ponds = (
            Pond.objects.filter(farm=farm, deleted_at__isnull=True)
            .exclude(status=Pond.Status.INACTIVE)
            .order_by("-id")
        )
        ponds = _filter_ponds_for_operario(ponds, request, farm)
        return Response(PondSerializer(ponds, many=True).data)


class PondDetailView(APIView):

    def get_permissions(self):
        if self.request.method in ("PATCH", "DELETE"):
            return [AdminOr(CanManagePond)()]
        return [AdminOr(IsFarmMember)()]

    def get(self, request, farm_id, pond_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        pond = get_pond_or_404(farm, pond_id)
        if not pond:
            return _pond_not_found_response()

        if request.user.role.name == "Operario":
            if not UserFarmPond.objects.filter(
                user=request.user, farm=farm, pond=pond
            ).exists():
                return _pond_forbidden_for_operario_response()

        return Response(PondSerializer(pond).data)

    def patch(self, request, farm_id, pond_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        pond = get_pond_or_404(farm, pond_id)
        if not pond:
            return _pond_not_found_response()

        serializer = PondSerializer(
            pond,
            data=request.data,
            partial=True,
            context={"request": request, "farm": farm},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, farm_id, pond_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        pond = get_pond_or_404(farm, pond_id)
        if not pond:
            return _pond_not_found_response()

        try:
            soft_delete_pond(pond)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(status=status.HTTP_204_NO_CONTENT)


class PondMemberListView(APIView):

    def get_permissions(self):
        return [AdminOr(CanManageFarmUsers)()]

    def get(self, request, farm_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        members = UserFarmPond.objects.filter(
            farm=farm,
        ).select_related("user", "pond")
        return Response(UserFarmPondSerializer(members, many=True).data)


class PondMemberDetailView(APIView):

    def get_permissions(self):
        return [AdminOr(CanManageFarmUsers)()]

    def get(self, request, farm_id, pond_id, user_id):
        farm = _get_farm(farm_id)
        pond = get_pond_or_404(farm, pond_id) if farm else None
        if not farm or not pond:
            return Response(
                {"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            member = UserFarmPond.objects.select_related("user").get(
                farm=farm, pond=pond, user_id=user_id
            )
        except UserFarmPond.DoesNotExist:
            return Response(
                {"detail": "Operario no encontrado en este estanque."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(UserFarmPondSerializer(member).data)

    def post(self, request, farm_id, pond_id, user_id):
        farm = _get_farm(farm_id)
        pond = get_pond_or_404(farm, pond_id) if farm else None
        if not farm or not pond:
            return Response(
                {"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        User = apps.get_model("accounts", "User")
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = UserFarmPondSerializer(
            data={"user": user.pk},
            context={"request": request, "farm": farm, "pond": pond},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(farm=farm, pond=pond)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, farm_id, pond_id, user_id):
        farm = _get_farm(farm_id)
        pond = get_pond_or_404(farm, pond_id) if farm else None
        if not farm or not pond:
            return Response(
                {"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        removed = remove_pond_member(farm, pond, user_id)
        if not removed:
            return Response(
                {"detail": "Operario no encontrado en este estanque."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PondInactivateView(APIView):

    def get_permissions(self):
        return [AdminOr(CanManagePond)()]

    def patch(self, request, farm_id, pond_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        pond = get_pond_or_404(farm, pond_id)
        if not pond:
            return _pond_not_found_response()

        if pond_has_cycles(pond):
            return Response(
                {
                    "detail": "No se puede inactivar un estanque que tiene ciclos asociados."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        pond.status = Pond.Status.INACTIVE
        pond.save(update_fields=["status"])
        return Response(PondSerializer(pond).data)


class PondActivateView(APIView):

    def get_permissions(self):
        return [AdminOr(CanManagePond)()]

    def patch(self, request, farm_id, pond_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        pond = get_pond_or_404(farm, pond_id)
        if not pond:
            return _pond_not_found_response()

        pond.status = Pond.Status.ACTIVE
        pond.save(update_fields=["status"])
        return Response(PondSerializer(pond).data)
