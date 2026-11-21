# validators.py

from decimal import Decimal

from django.apps import apps
from rest_framework import serializers

WEIGHT_TOLERANCE_G = Decimal("10")


def decimal_weights_equal(left, right, tolerance: Decimal = WEIGHT_TOLERANCE_G) -> bool:
    return abs(Decimal(left) - Decimal(right)) <= tolerance


def validate_biological_state(value: str) -> str:
    Batch = apps.get_model("batch", "Batch")
    valid = {choice for choice, _ in Batch.BiologicalState.choices}
    if value not in valid:
        raise serializers.ValidationError(
            f"biological_state inválido. Valores permitidos: {', '.join(sorted(valid))}."
        )
    return value


def validate_pond_for_derivation(*, farm_id: int, pond_id: int) -> object:
    Pond = apps.get_model("ponds", "Pond")

    try:
        pond = Pond.objects.get(pk=pond_id)
    except Pond.DoesNotExist:
        raise serializers.ValidationError(
            {"pond_id": f"El estanque {pond_id} no existe."}
        ) from None

    if pond.farm_id != farm_id:
        raise serializers.ValidationError(
            {"pond_id": "El estanque no pertenece a esta granja."}
        )

    if pond.deleted_at is not None:
        raise serializers.ValidationError(
            {"pond_id": "El estanque no está disponible (eliminado)."}
        )

    if pond.status == Pond.Status.INACTIVE:
        raise serializers.ValidationError(
            {
                "pond_id": (
                    f"El estanque está en estado '{pond.get_status_display()}'. "
                    "No se pueden derivar lotes a estanques inactivos."
                )
            }
        )

    return pond


def validate_specie_for_derivation(*, specie_id: int, cycle) -> object:
    Specie = apps.get_model("species", "Specie")

    try:
        specie = Specie.objects.get(pk=specie_id)
    except Specie.DoesNotExist:
        raise serializers.ValidationError(
            {"specie_id": f"La especie {specie_id} no existe."}
        ) from None

    if specie_id != cycle.specie_id:
        raise serializers.ValidationError(
            {
                "specie_id": (
                    "La especie debe coincidir con la especie del ciclo de la cosecha "
                    f"(esperada: {cycle.specie_id})."
                )
            }
        )

    return specie
