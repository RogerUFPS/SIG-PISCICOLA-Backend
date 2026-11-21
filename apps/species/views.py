from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Specie, SpecieFeedingReference, SpecieParameter, SpeciePondType, SpecieProductionReference
from .permissions import SpeciePermission
from .serializers import (
    SpecieFeedingReferenceSerializer,
    SpecieParameterSerializer,
    SpeciePondTypeSerializer,
    SpecieProductionReferenceSerializer,
    SpecieSerializer,
)


def _get_specie_or_404(specie_id):
    try:
        return Specie.objects.get(pk=specie_id)
    except Specie.DoesNotExist:
        return None


def _specie_not_found_response():
    return Response({"detail": "Especie no encontrada."}, status=status.HTTP_404_NOT_FOUND)


class SpecieListCreateView(APIView):
    serializer_class = SpecieSerializer
    permission_classes = [SpeciePermission]

    def get(self, request):
        species = Specie.objects.order_by("name")
        return Response(SpecieSerializer(species, many=True).data)

    def post(self, request):
        serializer = SpecieSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SpecieDetailView(APIView):
    serializer_class = SpecieSerializer
    permission_classes = [SpeciePermission]

    def get(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        return Response(SpecieSerializer(specie).data)

    def patch(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        serializer = SpecieSerializer(specie, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        specie.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SpeciePondTypeListCreateView(APIView):
    serializer_class = SpeciePondTypeSerializer
    permission_classes = [SpeciePermission]

    def get(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        qs = SpeciePondType.objects.filter(specie=specie)
        pond_type = request.query_params.get("pond_type")
        if pond_type:
            qs = qs.filter(pond_type=pond_type)
        return Response(SpeciePondTypeSerializer(qs.order_by("id"), many=True).data)

    def post(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        serializer = SpeciePondTypeSerializer(
            data=request.data, context={"specie": specie}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(specie=specie)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SpeciePondTypeDetailView(APIView):
    serializer_class = SpeciePondTypeSerializer
    permission_classes = [SpeciePermission]

    def _get_object(self, specie, pond_type_id):
        try:
            return SpeciePondType.objects.get(pk=pond_type_id, specie=specie)
        except SpeciePondType.DoesNotExist:
            return None

    def get(self, request, specie_id, pond_type_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, pond_type_id)
        if not obj:
            return Response({"detail": "Tipo de estanque no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SpeciePondTypeSerializer(obj).data)

    def patch(self, request, specie_id, pond_type_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, pond_type_id)
        if not obj:
            return Response({"detail": "Tipo de estanque no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SpeciePondTypeSerializer(
            obj, data=request.data, partial=True, context={"specie": specie}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, specie_id, pond_type_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, pond_type_id)
        if not obj:
            return Response({"detail": "Tipo de estanque no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SpecieParameterListCreateView(APIView):
    serializer_class = SpecieParameterSerializer
    permission_classes = [SpeciePermission]

    def get(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        qs = SpecieParameter.objects.filter(specie=specie)
        parameter_type = request.query_params.get("parameter_type")
        if parameter_type:
            qs = qs.filter(parameter_type=parameter_type)
        return Response(SpecieParameterSerializer(qs.order_by("id"), many=True).data)

    def post(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        serializer = SpecieParameterSerializer(
            data=request.data, context={"specie": specie}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(specie=specie)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SpecieParameterDetailView(APIView):
    serializer_class = SpecieParameterSerializer
    permission_classes = [SpeciePermission]

    def _get_object(self, specie, parameter_id):
        try:
            return SpecieParameter.objects.get(pk=parameter_id, specie=specie)
        except SpecieParameter.DoesNotExist:
            return None

    def get(self, request, specie_id, parameter_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, parameter_id)
        if not obj:
            return Response({"detail": "Parámetro no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SpecieParameterSerializer(obj).data)

    def patch(self, request, specie_id, parameter_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, parameter_id)
        if not obj:
            return Response({"detail": "Parámetro no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SpecieParameterSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, specie_id, parameter_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, parameter_id)
        if not obj:
            return Response({"detail": "Parámetro no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SpecieFeedingReferenceListCreateView(APIView):
    serializer_class = SpecieFeedingReferenceSerializer
    permission_classes = [SpeciePermission]

    def get(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        qs = SpecieFeedingReference.objects.filter(specie=specie)
        stage = request.query_params.get("stage")
        if stage:
            qs = qs.filter(stage=stage)
        feed_form = request.query_params.get("feed_form") or request.query_params.get(
            "recommended_feed_form"
        )
        if feed_form:
            qs = qs.filter(recommended_feed_form=feed_form)
        return Response(SpecieFeedingReferenceSerializer(qs.order_by("id"), many=True).data)

    def post(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        serializer = SpecieFeedingReferenceSerializer(
            data=request.data, context={"specie": specie}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(specie=specie)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SpecieFeedingReferenceDetailView(APIView):
    serializer_class = SpecieFeedingReferenceSerializer
    permission_classes = [SpeciePermission]

    def _get_object(self, specie, ref_id):
        try:
            return SpecieFeedingReference.objects.get(pk=ref_id, specie=specie)
        except SpecieFeedingReference.DoesNotExist:
            return None

    def get(self, request, specie_id, ref_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, ref_id)
        if not obj:
            return Response({"detail": "Referencia de alimentación no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SpecieFeedingReferenceSerializer(obj).data)

    def patch(self, request, specie_id, ref_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, ref_id)
        if not obj:
            return Response({"detail": "Referencia de alimentación no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SpecieFeedingReferenceSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, specie_id, ref_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, ref_id)
        if not obj:
            return Response({"detail": "Referencia de alimentación no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SpecieProductionReferenceListCreateView(APIView):
    serializer_class = SpecieProductionReferenceSerializer
    permission_classes = [SpeciePermission]

    def get(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        qs = SpecieProductionReference.objects.filter(specie=specie)
        ref_type = request.query_params.get("type")
        if ref_type:
            qs = qs.filter(type=ref_type)
        return Response(SpecieProductionReferenceSerializer(qs.order_by("id"), many=True).data)

    def post(self, request, specie_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        serializer = SpecieProductionReferenceSerializer(
            data=request.data, context={"specie": specie}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(specie=specie)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SpecieProductionReferenceDetailView(APIView):
    serializer_class = SpecieProductionReferenceSerializer
    permission_classes = [SpeciePermission]

    def _get_object(self, specie, ref_id):
        try:
            return SpecieProductionReference.objects.get(pk=ref_id, specie=specie)
        except SpecieProductionReference.DoesNotExist:
            return None

    def get(self, request, specie_id, ref_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, ref_id)
        if not obj:
            return Response({"detail": "Referencia de producción no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(SpecieProductionReferenceSerializer(obj).data)

    def patch(self, request, specie_id, ref_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, ref_id)
        if not obj:
            return Response({"detail": "Referencia de producción no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SpecieProductionReferenceSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, specie_id, ref_id):
        specie = _get_specie_or_404(specie_id)
        if not specie:
            return _specie_not_found_response()
        obj = self._get_object(specie, ref_id)
        if not obj:
            return Response({"detail": "Referencia de producción no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
