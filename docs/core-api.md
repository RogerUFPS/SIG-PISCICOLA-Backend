# Endpoints de Core

Todas las rutas están bajo `/api`. Las rutas de Alertas y AuditLog requieren el
identificador de la finca en la URL; el permiso de lectura de cada recurso se
otorga por separado en `module_permissions` del rol de finca: `alerts` o
`audit_logs`. Consulta la [guía de permisos para frontend](./frontend-permissions-guide.md).

## Unidades

### `GET /api/unit/`

Lista las unidades disponibles. No admite parámetros de consulta.

### `GET /api/unit/<id>/`

Obtiene una unidad.

Los campos de cada elemento son:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | integer | Identificador. |
| `symbol` | string | Símbolo de la unidad. |
| `name` | string | Nombre de la unidad. |

Estas rutas solo permiten lectura.

## Alertas

### `GET /api/farms/core/<farm_id>/alerts/`

Lista las alertas de la finca indicada. Parámetros de consulta opcionales:

| Parámetro | Valores | Descripción |
| --- | --- | --- |
| `source_type` | `Health`, `Stock`, `Ambiental`, `Control`, `Feeding`, `Sale` | Filtra por fuente. |
| `severity` | `low`, `medium`, `high`, `critical` | Filtra por severidad. |
| `is_resolved` | `true`, `false` | Filtra por estado de resolución. |

### `GET /api/farms/core/<farm_id>/alerts/<id>/`

Obtiene una alerta de esa finca. Una alerta contiene:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | integer | Identificador. |
| `farm` | integer | Identificador de la finca. |
| `pond` | integer o `null` | Estanque relacionado, si existe. |
| `cycle` | integer o `null` | Ciclo relacionado, si existe. |
| `source_type` | string | Fuente; opciones indicadas arriba. |
| `source_id` | integer o `null` | Identificador del registro de origen. |
| `description` | string | Descripción breve. |
| `message` | string | Mensaje de la alerta. |
| `value` | number o `null` | Valor registrado, si aplica. |
| `threshold` | number o `null` | Umbral relacionado, si aplica. |
| `severity` | string | `low`, `medium`, `high` o `critical`. |
| `is_resolved` | boolean | Indica si está resuelta. |
| `resolved_at` | fecha/hora o `null` | Fecha de resolución. |
| `resolved_by` | integer o `null` | Identificador de quien la resolvió. |
| `resolved_by_name` | string o `null` | Nombre de quien la resolvió. |
| `created_at` | fecha/hora | Fecha de creación. |

Alertas solo permite `GET` de lista y detalle; no acepta creación,
actualización, resolución ni eliminación.

## AuditLog

### `GET /api/farms/core/<farm_id>/auditlogs/`

Lista los registros de auditoría de la finca indicada. Requiere acceso a la
finca y permiso `audit_logs.view`; cada respuesta contiene como
máximo 50 registros y usa paginación (`count`, `next`, `previous`, `results`).
La página se solicita con `?page=<n>`; no existe una opción para desactivar la
paginación ni aumentar el tamaño de página.

### `GET /api/farms/core/<farm_id>/auditlogs/<id>/`

Obtiene un registro de auditoría de esa finca. Cada elemento contiene:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | integer | Identificador. |
| `user` | integer o `null` | Identificador del usuario relacionado. |
| `user_name` | string o `null` | Nombre completo del usuario que realizó el cambio; si no tiene nombre, contiene su correo. |
| `farm_id` | integer o `null` | Identificador de la finca relacionada. |
| `description` | string | Descripción del cambio. |
| `type_source` | string | Tipo de entidad que originó el registro. |
| `source_id` | integer o `null` | Identificador de la entidad de origen. |
| `ip` | string o `null` | Dirección IP registrada. |
| `old_values` | object o `null` | Valores previos, si están disponibles. |
| `new_values` | object o `null` | Valores nuevos, si están disponibles. |
| `created_at` | fecha/hora | Fecha de creación. |

`type_source` puede ser: `User`, `UserFarm`, `Farm`, `FarmRole`,
`FarmRoleAppPermission`, `Pond`,
`UserFarmPond`, `TypeProduct`, `Product`, `PurchaseDetail`, `Supplier`,
`Specie`, `SpecieParameter`, `SpecieFeedingReference`,
`SpecieProductionReference`, `Batch`, `ProductionPlan`, `Cycle`,
`FeedingSchedule`, `FeedingPlan`, `FeedingEvent`, `DailyStat`,
`ProductUsageLog`, `ControlStat`, `FishEvaluated`, `HealthStat`,
`TreatmentPlan`, `TreatmentEvent`, `AmbientalMeasurement`, `Alert`, `Sale`,
`InventoryMovement`, `Harvest`, `HarvestClassification`, `Client`, `Buy`,
`Invitation`, `BatchTransfer`, `GradingEvent`, `SaleDetail`,
`CyclePondBatch`, `PondBatch`, `SpeciePondType` o `ProductionReport`.

Los cambios registrados en entidades de una finca generan entradas de
auditoría con usuario e IP cuando están disponibles, valores anteriores y
nuevos, y fecha. Los registros de una finca nunca incluyen los de otra. Los
registros son inmutables: solo permiten `GET` de lista y detalle; no aceptan
creación desde la API, actualización ni eliminación.
