from django.apps import apps
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import AdminOr, AppPermission
from apps.farms.permissions import CanManageCycle, IsFarmMember

from .models import FeedingEvent, FeedingPlan, FeedingSchedule
from .serializers import (
    FeedingEventSerializer,
    FeedingEventUpdateSerializer,
    FeedingPlanReplaceSerializer,
    FeedingPlanSerializer,
    FeedingScheduleSerializer,
)
from .utils import (
    feeding_plan_lifecycle_state,
    update_in_progress_feeding_plan,
    update_scheduled_feeding_plan,
)


def _confirm_warnings_requested(request) -> bool:
    return str(request.query_params.get("confirm_warnings", "")).lower() in (
        "true",
        "1",
        "yes",
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


def _plan_not_found_response():
    return Response(
        {"detail": "Plan de alimentación no encontrado."},
        status=status.HTTP_404_NOT_FOUND,
    )


def _event_not_found_response():
    return Response(
        {"detail": "Evento de alimentación no encontrado."},
        status=status.HTTP_404_NOT_FOUND,
    )


def _schedule_not_found_response():
    return Response(
        {"detail": "Cronograma de alimentación no encontrado."},
        status=status.HTTP_404_NOT_FOUND,
    )


def _cycle_not_found_response():
    return Response(
        {"detail": "Ciclo no encontrado."},
        status=status.HTTP_404_NOT_FOUND,
    )


def _get_cycle_in_farm(farm_id: int, cycle_id: int):
    Cycle = apps.get_model("cycle", "Cycle")
    try:
        return Cycle.objects.get(
            pk=cycle_id, farm_id=farm_id, deleted_at__isnull=True
        )
    except Cycle.DoesNotExist:
        return None


def _get_cycle_in_pond(farm_id: int, pond_id: int, cycle_id: int):
    """Valida que el ciclo exista en la granja Y pertenezca al estanque."""
    Cycle = apps.get_model("cycle", "Cycle")
    try:
        return Cycle.objects.get(
            pk=cycle_id, farm_id=farm_id, pond_id=pond_id, deleted_at__isnull=True
        )
    except Cycle.DoesNotExist:
        return None


def _bad_request(detail: str):
    return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _parse_optional_id(params, key: str):
    raw = params.get(key)
    if raw is None or raw == "":
        return None, None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None, _bad_request(f"Parámetro '{key}' debe ser un entero válido.")
    if v < 1:
        return None, _bad_request(f"Parámetro '{key}' debe ser mayor a 0.")
    return v, None


def _parse_schedule_type_param(params):
    raw = params.get("type")
    if raw is None or raw == "":
        return None, None
    valid = {c[0] for c in FeedingSchedule.Stage.choices}
    if raw not in valid:
        return None, _bad_request(
            f"Parámetro 'type' inválido. Valores: {', '.join(sorted(valid))}."
        )
    return raw, None


def _choices_payload(choices) -> list[dict]:
    """Lista {value, label} para enums del modelo (TextChoices)."""
    return [{"value": v, "label": lbl} for v, lbl in choices]


class FeedingOptionsView(APIView):
    """
    Catálogo de valores permitidos para formularios (cronogramas, eventos).

    GET sin farm_id: solo expone opciones definidas en modelos ``feeding``.
    """

    permission_classes = [IsAuthenticated, AppPermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response(
            {
                "feeding_schedule": {
                    "type": _choices_payload(FeedingSchedule.Stage.choices),
                    "feed_form": _choices_payload(FeedingSchedule.FeedForm.choices),
                },
                "feeding_event": {
                    "status": _choices_payload(FeedingEvent.Status.choices),
                },
            }
        )


class FeedingScheduleListCreateView(APIView):

    def get_permissions(self):
        if self.request.method == "GET":
            return [AdminOr(IsFarmMember)()]
        return [AdminOr(CanManageCycle)()]

    @extend_schema(
        parameters=[
            OpenApiParameter("specie", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("product", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("type", OpenApiTypes.STR, OpenApiParameter.QUERY),
        ],
        responses={200: FeedingScheduleSerializer(many=True)},
    )
    def get(self, request, farm_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()

        specie_id, err = _parse_optional_id(request.query_params, "specie")
        if err:
            return err
        product_id, err = _parse_optional_id(request.query_params, "product")
        if err:
            return err
        schedule_type, err = _parse_schedule_type_param(request.query_params)
        if err:
            return err

        qs = (
            FeedingSchedule.objects.filter(
                farm=farm,
                deleted_at__isnull=True,
                is_current=True,
            )
            .select_related("product", "specie", "parent")
        )
        if specie_id is not None:
            qs = qs.filter(specie_id=specie_id)
        if product_id is not None:
            qs = qs.filter(product_id=product_id)
        if schedule_type is not None:
            qs = qs.filter(type=schedule_type)

        qs = qs.order_by("-created_at")
        return Response(FeedingScheduleSerializer(qs, many=True).data)

    @extend_schema(
        request=FeedingScheduleSerializer,
        responses={201: FeedingScheduleSerializer},
        parameters=[
            OpenApiParameter(
                name="confirm_warnings",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Si es true, guarda aunque existan advertencias respecto a la "
                    "referencia técnica. Sin este parámetro, el POST devuelve 400 "
                    "con las advertencias para que el usuario confirme."
                ),
            ),
        ],
    )
    def post(self, request, farm_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()
        serializer = FeedingScheduleSerializer(
            data=request.data,
            context={
                "farm": farm,
                "confirm_warnings": _confirm_warnings_requested(request),
            },
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(farm=farm)
        return Response(FeedingScheduleSerializer(instance).data, status=status.HTTP_201_CREATED)


class FeedingScheduleDetailView(APIView):

    def get_permissions(self):
        if self.request.method == "GET":
            return [AdminOr(IsFarmMember)()]
        return [AdminOr(CanManageCycle)()]

    def _get_schedule(self, farm_id, schedule_id):
        try:
            return FeedingSchedule.objects.select_related(
                "product", "specie", "parent"
            ).get(
                pk=schedule_id,
                farm_id=farm_id,
                deleted_at__isnull=True,
                is_current=True,
            )
        except FeedingSchedule.DoesNotExist:
            return None

    @extend_schema(responses={200: FeedingScheduleSerializer})
    def get(self, request, farm_id, schedule_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        schedule = self._get_schedule(farm_id, schedule_id)
        if not schedule:
            return _schedule_not_found_response()
        return Response(FeedingScheduleSerializer(schedule).data)

    @extend_schema(
        request=FeedingScheduleSerializer,
        responses={200: FeedingScheduleSerializer},
        parameters=[
            OpenApiParameter(
                name="confirm_warnings",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Si es true, publica la nueva versión aunque existan advertencias "
                    "respecto a la referencia técnica."
                ),
            ),
        ],
    )
    def patch(self, request, farm_id, schedule_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        schedule = self._get_schedule(farm_id, schedule_id)
        if not schedule:
            return _schedule_not_found_response()
        serializer = FeedingScheduleSerializer(
            schedule,
            data=request.data,
            partial=True,
            context={"confirm_warnings": _confirm_warnings_requested(request)},
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(FeedingScheduleSerializer(instance).data, status=status.HTTP_200_OK)

    @extend_schema(responses={204: None})
    def delete(self, request, farm_id, schedule_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        schedule = self._get_schedule(farm_id, schedule_id)
        if not schedule:
            return _schedule_not_found_response()
        if FeedingPlan.objects.filter(
            feeding_schedule_id=schedule.pk,
            deleted_at__isnull=True,
        ).exists():
            return Response(
                {
                    "detail": (
                        "No puede eliminar el cronograma mientras existan planes de "
                        "alimentación vigentes asociados a él."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )
        now = timezone.now()
        schedule.is_current = False
        schedule.deleted_at = now
        schedule.save(update_fields=["is_current", "deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class FeedingScheduleVersionsListView(APIView):

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    @extend_schema(responses={200: FeedingScheduleSerializer(many=True)})
    def get(self, request, farm_id, schedule_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        try:
            head = FeedingSchedule.objects.select_related(
                "product", "specie", "parent"
            ).get(
                pk=schedule_id,
                farm_id=farm_id,
                is_current=True,
                deleted_at__isnull=True,
            )
        except FeedingSchedule.DoesNotExist:
            return _schedule_not_found_response()

        chain = []
        cur = head
        seen: set[int] = set()
        while cur is not None and cur.pk not in seen:
            seen.add(cur.pk)
            chain.append(cur)
            pid = cur.parent_id
            if not pid:
                break
            cur = (
                FeedingSchedule.objects.select_related(
                    "product", "specie", "parent"
                )
                .filter(pk=pid, farm_id=farm_id)
                .first()
            )
        chain.reverse()
        return Response(FeedingScheduleSerializer(chain, many=True).data)


class FarmFeedingSchedulePlansListView(APIView):
    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    @extend_schema(
        parameters=[
            OpenApiParameter("cycle", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: FeedingPlanSerializer(many=True)},
    )
    def get(self, request, farm_id, schedule_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_schedule_head_for_farm(farm_id, schedule_id):
            return _schedule_not_found_response()

        qs = FeedingPlan.objects.filter(
            farm_id=farm_id,
            feeding_schedule_id=schedule_id,
        ).select_related("cycle", "feeding_schedule", "farm")
        if not AdminOr(CanManageCycle)().has_permission(request, self):
            qs = qs.filter(deleted_at__isnull=True)
        cycle_param = request.query_params.get("cycle")
        if cycle_param is not None:
            qs = qs.filter(cycle_id=cycle_param)
        qs = qs.order_by("-created_at")
        return Response(FeedingPlanSerializer(qs, many=True).data)


class FeedingPlanOccupiedRangesView(APIView):

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, farm_id, cycle_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_cycle_in_farm(farm_id, cycle_id):
            return _cycle_not_found_response()

        qs = (
            FeedingPlan.objects.filter(
                farm_id=farm_id,
                cycle_id=cycle_id,
                deleted_at__isnull=True,
            )
            .order_by("start_date", "pk")
            .values("start_date", "end_date")
        )
        ranges = list(qs)
        return Response({"cycle": cycle_id, "ranges": ranges})


def _get_feeding_plan_for_farm(
    farm_id, plan_id, *, current_only: bool = False, cycle_id: int | None = None
):
    try:
        qs = FeedingPlan.objects.select_related(
            "cycle", "feeding_schedule", "farm"
        ).filter(pk=plan_id, farm_id=farm_id)
        if cycle_id is not None:
            qs = qs.filter(cycle_id=cycle_id)
        if current_only:
            qs = qs.filter(deleted_at__isnull=True)
        return qs.get()
    except FeedingPlan.DoesNotExist:
        return None


def _get_schedule_head_for_farm(farm_id: int, schedule_id: int):
    try:
        return FeedingSchedule.objects.get(
            pk=schedule_id,
            farm_id=farm_id,
            deleted_at__isnull=True,
            is_current=True,
        )
    except FeedingSchedule.DoesNotExist:
        return None


def _get_plan_for_farm_schedule(
    farm_id: int, schedule_id: int, plan_id: int, *, current_only: bool = False
):
    try:
        qs = FeedingPlan.objects.select_related(
            "cycle", "feeding_schedule", "farm"
        ).filter(
            pk=plan_id,
            farm_id=farm_id,
            feeding_schedule_id=schedule_id,
        )
        if current_only:
            qs = qs.filter(deleted_at__isnull=True)
        return qs.get()
    except FeedingPlan.DoesNotExist:
        return None


class FarmFeedingSchedulePlanDetailView(APIView):
    """Detalle de plan solo lectura: granja → cronograma → plan."""

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    @extend_schema(responses={200: FeedingPlanSerializer})
    def get(self, request, farm_id, schedule_id, plan_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_schedule_head_for_farm(farm_id, schedule_id):
            return _schedule_not_found_response()
        plan = _get_plan_for_farm_schedule(
            farm_id, schedule_id, plan_id, current_only=False
        )
        if not plan:
            return _plan_not_found_response()
        if plan.deleted_at is not None and not AdminOr(CanManageCycle)().has_permission(
            request, self
        ):
            return _plan_not_found_response()
        return Response(FeedingPlanSerializer(plan).data)


class CycleFeedingPlanListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [AdminOr(IsFarmMember)()]
        return [AdminOr(CanManageCycle)()]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "feeding_schedule", OpenApiTypes.INT, OpenApiParameter.QUERY
            ),
        ],
        responses={200: FeedingPlanSerializer(many=True)},
    )
    def get(self, request, farm_id, pond_id, cycle_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_cycle_in_pond(farm_id, pond_id, cycle_id):
            return _cycle_not_found_response()

        qs = FeedingPlan.objects.filter(
            farm_id=farm_id, cycle_id=cycle_id, cycle__pond_id=pond_id
        ).select_related("cycle", "feeding_schedule", "farm")
        if not AdminOr(CanManageCycle)().has_permission(request, self):
            qs = qs.filter(deleted_at__isnull=True)
        schedule_id, err = _parse_optional_id(request.query_params, "feeding_schedule")
        if err:
            return err
        if schedule_id is not None:
            qs = qs.filter(feeding_schedule_id=schedule_id)
        qs = qs.order_by("-created_at")
        return Response(FeedingPlanSerializer(qs, many=True).data)

    @extend_schema(request=FeedingPlanSerializer, responses={201: FeedingPlanSerializer})
    def post(self, request, farm_id, pond_id, cycle_id):
        farm = _get_farm(farm_id)
        if not farm:
            return _farm_not_found_response()
        if not _get_cycle_in_pond(farm_id, pond_id, cycle_id):
            return _cycle_not_found_response()

        body = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        raw_cycle = body.get("cycle")
        if raw_cycle is not None:
            try:
                if int(raw_cycle) != cycle_id:
                    return _bad_request(
                        "El campo «cycle» del cuerpo debe coincidir con el ciclo de la URL."
                    )
            except (TypeError, ValueError):
                return _bad_request("El campo «cycle» debe ser un entero válido.")
        body["cycle"] = cycle_id

        serializer = FeedingPlanSerializer(
            data=body,
            context={"farm": farm, "fixed_cycle_id": cycle_id},
        )
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return Response(
            FeedingPlanSerializer(instance).data, status=status.HTTP_201_CREATED
        )


class CycleFeedingPlanDetailView(APIView):

    def get_permissions(self):
        if self.request.method == "GET":
            return [AdminOr(IsFarmMember)()]
        return [AdminOr(CanManageCycle)()]

    @extend_schema(responses={200: FeedingPlanSerializer})
    def get(self, request, farm_id, pond_id, cycle_id, plan_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_cycle_in_pond(farm_id, pond_id, cycle_id):
            return _cycle_not_found_response()
        plan = _get_feeding_plan_for_farm(
            farm_id, plan_id, current_only=False, cycle_id=cycle_id
        )
        if not plan:
            return _plan_not_found_response()
        if plan.deleted_at is not None and not AdminOr(CanManageCycle)().has_permission(
            request, self
        ):
            return _plan_not_found_response()
        return Response(FeedingPlanSerializer(plan).data)

    @extend_schema(
        request=FeedingPlanReplaceSerializer,
        responses={200: FeedingPlanSerializer, 201: FeedingPlanSerializer},
    )
    def patch(self, request, farm_id, pond_id, cycle_id, plan_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_cycle_in_pond(farm_id, pond_id, cycle_id):
            return _cycle_not_found_response()
        plan = _get_feeding_plan_for_farm(
            farm_id, plan_id, current_only=True, cycle_id=cycle_id
        )
        if not plan:
            return _plan_not_found_response()

        state = feeding_plan_lifecycle_state(plan)
        if state == "finished":
            return Response(
                {
                    "detail": (
                        "No se puede modificar un plan cuya fecha de fin ya pasó."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = FeedingPlanReplaceSerializer(
            data=request.data,
            context={"plan": plan, "farm_id": farm_id},
        )
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            if state == "in_progress":
                new_plan = update_in_progress_feeding_plan(
                    farm_id=farm_id,
                    old_plan=plan,
                    cycle=vd["cycle"],
                    feeding_schedule=vd["feeding_schedule"],
                    start_date=vd["start_date"],
                    end_date=vd["end_date"],
                )
                return Response(
                    FeedingPlanSerializer(new_plan).data,
                    status=status.HTTP_201_CREATED,
                )
            updated_plan = update_scheduled_feeding_plan(
                farm_id=farm_id,
                plan=plan,
                cycle=vd["cycle"],
                feeding_schedule=vd["feeding_schedule"],
                start_date=vd["start_date"],
                end_date=vd["end_date"],
            )
            return Response(FeedingPlanSerializer(updated_plan).data)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @extend_schema(responses={204: None})
    def delete(self, request, farm_id, pond_id, cycle_id, plan_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_cycle_in_pond(farm_id, pond_id, cycle_id):
            return _cycle_not_found_response()
        plan = _get_feeding_plan_for_farm(
            farm_id, plan_id, current_only=True, cycle_id=cycle_id
        )
        if not plan:
            return _plan_not_found_response()
        if feeding_plan_lifecycle_state(plan) == "in_progress":
            return Response(
                {
                    "detail": (
                        "No puede eliminar un plan en curso. Solo se permiten bajas "
                        "lógicas de planes programados o ya terminados."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        plan.deleted_at = timezone.now()
        plan.save(update_fields=["deleted_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class FarmFeedingSchedulePlanEventListView(APIView):

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    @extend_schema(
        parameters=[
            OpenApiParameter("cycle", OpenApiTypes.INT, OpenApiParameter.QUERY),
            OpenApiParameter("pond", OpenApiTypes.INT, OpenApiParameter.QUERY),
        ],
        responses={200: FeedingEventSerializer(many=True)},
    )
    def get(self, request, farm_id, schedule_id, plan_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_schedule_head_for_farm(farm_id, schedule_id):
            return _schedule_not_found_response()

        plan = _get_plan_for_farm_schedule(
            farm_id, schedule_id, plan_id, current_only=False
        )
        if not plan:
            return _plan_not_found_response()
        if plan.deleted_at is not None and not AdminOr(CanManageCycle)().has_permission(
            request, self
        ):
            return _plan_not_found_response()

        qs = FeedingEvent.objects.filter(
            farm_id=farm_id,
            feeding_plan_id=plan_id,
        ).select_related(
            "cycle",
            "feeding_plan",
            "farm",
            "planned_unit",
            "actual_unit",
            "completed_by",
        )
        cycle_param = request.query_params.get("cycle")
        if cycle_param is not None:
            qs = qs.filter(cycle_id=cycle_param)
        pond_id, err = _parse_optional_id(request.query_params, "pond")
        if err:
            return err
        if pond_id is not None:
            qs = qs.filter(cycle__cyclepondbatch__pond_batch__pond_id=pond_id).distinct()
        qs = qs.order_by("date", "scheduled_time", "ration_number")
        return Response(FeedingEventSerializer(qs, many=True).data)


class FarmFeedingSchedulePlanEventDetailView(APIView):

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    def _get_event(self, farm_id, plan_id, event_id):
        try:
            return FeedingEvent.objects.select_related(
                "cycle",
                "feeding_plan",
                "farm",
                "planned_unit",
                "actual_unit",
                "completed_by",
            ).get(
                pk=event_id,
                farm_id=farm_id,
                feeding_plan_id=plan_id,
            )
        except FeedingEvent.DoesNotExist:
            return None

    @extend_schema(responses={200: FeedingEventSerializer})
    def get(self, request, farm_id, schedule_id, plan_id, event_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_schedule_head_for_farm(farm_id, schedule_id):
            return _schedule_not_found_response()

        plan = _get_plan_for_farm_schedule(
            farm_id, schedule_id, plan_id, current_only=False
        )
        if not plan:
            return _plan_not_found_response()
        if plan.deleted_at is not None and not AdminOr(CanManageCycle)().has_permission(
            request, self
        ):
            return _plan_not_found_response()

        event = self._get_event(farm_id, plan_id, event_id)
        if not event:
            return _event_not_found_response()
        return Response(FeedingEventSerializer(event).data)


class CycleFeedingEventListView(APIView):

    def get_permissions(self):
        return [AdminOr(IsFarmMember)()]

    @extend_schema(responses={200: FeedingEventSerializer(many=True)})
    def get(self, request, farm_id, pond_id, cycle_id, plan_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_cycle_in_pond(farm_id, pond_id, cycle_id):
            return _cycle_not_found_response()
        plan = _get_feeding_plan_for_farm(
            farm_id, plan_id, current_only=False, cycle_id=cycle_id
        )
        if not plan:
            return _plan_not_found_response()
        if plan.deleted_at is not None and not AdminOr(CanManageCycle)().has_permission(
            request, self
        ):
            return _plan_not_found_response()

        qs = FeedingEvent.objects.filter(
            farm_id=farm_id,
            cycle_id=cycle_id,
            feeding_plan_id=plan_id,
        ).select_related(
            "cycle",
            "feeding_plan",
            "farm",
            "planned_unit",
            "actual_unit",
            "completed_by",
        )
        qs = qs.order_by("date", "scheduled_time", "ration_number")
        return Response(FeedingEventSerializer(qs, many=True).data)


class CycleFeedingEventDetailView(APIView):

    def get_permissions(self):
        if self.request.method == "GET":
            return [AdminOr(IsFarmMember)()]
        return [AdminOr(CanManageCycle)()]

    def _get_event(self, farm_id, pond_id, cycle_id, plan_id, event_id):
        try:
            return FeedingEvent.objects.select_related(
                "cycle",
                "feeding_plan",
                "farm",
                "planned_unit",
                "actual_unit",
                "completed_by",
            ).get(
                pk=event_id,
                farm_id=farm_id,
                cycle_id=cycle_id,
                feeding_plan_id=plan_id,
                cycle__pond_id=pond_id,
            )
        except FeedingEvent.DoesNotExist:
            return None

    @extend_schema(responses={200: FeedingEventSerializer})
    def get(self, request, farm_id, pond_id, cycle_id, plan_id, event_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_cycle_in_pond(farm_id, pond_id, cycle_id):
            return _cycle_not_found_response()
        event = self._get_event(farm_id, pond_id, cycle_id, plan_id, event_id)
        if not event:
            return _event_not_found_response()
        if (
            event.feeding_plan.deleted_at is not None
            and not AdminOr(CanManageCycle)().has_permission(request, self)
        ):
            return _event_not_found_response()
        return Response(FeedingEventSerializer(event).data)

    @extend_schema(
        request=FeedingEventUpdateSerializer,
        responses={200: FeedingEventSerializer},
    )
    def patch(self, request, farm_id, pond_id, cycle_id, plan_id, event_id):
        if not _get_farm(farm_id):
            return _farm_not_found_response()
        if not _get_cycle_in_pond(farm_id, pond_id, cycle_id):
            return _cycle_not_found_response()
        event = self._get_event(farm_id, pond_id, cycle_id, plan_id, event_id)
        if not event:
            return _event_not_found_response()
        if (
            event.feeding_plan.deleted_at is not None
            and not AdminOr(CanManageCycle)().has_permission(request, self)
        ):
            return _event_not_found_response()
        serializer = FeedingEventUpdateSerializer(
            event,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        event.refresh_from_db()
        return Response(FeedingEventSerializer(event).data)