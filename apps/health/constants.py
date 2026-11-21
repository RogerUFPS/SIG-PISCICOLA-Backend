TREATMENT_PLAN_DATE_OVERLAP_MESSAGE = "Las fechas se solapan con otro plan de tratamiento vigente del mismo registro de salud."

# Nombres de TypeProduct permitidos para productos en planes de tratamiento.
TREATMENT_PLAN_PRODUCT_TYPE_NAMES = (
    "medicamento",
    "medicamentos",
    "Sanidad y bioseguridad",
    "medication",
    "medicine",
    "medicina",
    "drug",
    "farmaco",
    "fármaco",
    "farmacos",
    "fármacos",
)

# Tipo de evaluación de peces creada desde un POST combinado de HealthStat.
FISH_EVALUATED_TYPE_HEALTH_STAT = "health_stat"

# Campos write-only del POST combinado (formulario plano → FishEvaluated).
FISH_EVALUATION_CREATE_FIELDS = (
    "sampled_quantity",
    "mortality_quantity",
    "min_weight_g",
    "max_weight_g",
    "observations",
    "batch_id",
)
