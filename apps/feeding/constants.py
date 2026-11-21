FEED_SCHEDULE_PRODUCT_TYPE_NAMES = ("alimento", "feed", "food", "alimentacion", "alimentación")

MINUTES_PER_DAY = 1440

# Campos del cronograma autocompletables desde SpecieFeedingReference (POST).
FEEDING_SCHEDULE_REFERENCE_DEFAULT_FIELDS = (
    "pellet_size_mm",
    "feeding_rate_percentage",
    "expected_fca",
    "expected_daily_gain_g",
)

# Pesos: default solo si faltan ambos; si el usuario envía uno, debe enviar el otro.
FEEDING_SCHEDULE_REFERENCE_WEIGHT_FIELDS = (
    "aceptable_min_weight_g",
    "aceptable_max_weight_g",
)

# Campos que se pueden fusionar al versionar un cronograma (PATCH → nueva versión).
FEEDING_SCHEDULE_VERSION_MERGE_FIELDS = (
    "comments",
    "type",
    "aceptable_min_weight_g",
    "aceptable_max_weight_g",
    "feed_form",
    "pellet_size_mm",
    "feeding_rate_percentage",
    "times_per_day",
    "gap_between_times_per_day",
    "gap_between_completed_day",
    "expected_fca",
    "expected_daily_gain_g",
)

# Campos prohibidos al versionar un cronograma (PATCH sustitutivo).
FEEDING_SCHEDULE_PATCH_FORBIDDEN_MESSAGES = {
    "name": "El nombre se hereda del cronograma anterior; no se puede enviar al versionar.",
    "product": (
        "El producto se hereda del cronograma anterior; para otro alimento cree un "
        "cronograma nuevo (POST)."
    ),
    "specie": (
        "La especie se hereda del cronograma anterior; para otra especie cree un "
        "cronograma nuevo (POST)."
    ),
    "parent": (
        "No envíe parent: la nueva versión queda automáticamente ligada al "
        "cronograma que está actualizando."
    ),
    "version": "La versión la asigna el servidor al crear la nueva fila.",
    "is_current": (
        "La marca de versión vigente la define el sistema al crear la nueva versión."
    ),
}

FEEDING_SCHEDULE_CREATE_PARENT_MESSAGE = (
    "Al crear un cronograma nuevo no debe enviar parent. "
    "Para publicar una nueva versión, use el flujo de actualización "
    "del cronograma vigente que desea sustituir."
)

FEEDING_SCHEDULE_SYSTEM_ASSIGNED_FIELDS = ("version", "is_current")

FEEDING_SCHEDULE_SYSTEM_ASSIGNED_MESSAGE = (
    "Este campo lo asigna el sistema al crear el cronograma."
)

FEEDING_PLAN_DATE_OVERLAP_MESSAGE = (
    "Las fechas se solapan con otro plan vigente del mismo ciclo."
)
