# Endpoints de Core

Todas las rutas están bajo `/api`. Las rutas de Alertas y AuditLog requieren el
identificador de la finca en la URL; el permiso de lectura de cada recurso se
otorga por separado en `app_permissions` del rol de finca: `core_alerts` o
`core_auditlogs`.

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

Lista los registros de auditoría de la finca indicada.

### `GET /api/farms/core/<farm_id>/auditlogs/<id>/`

Obtiene un registro de auditoría de esa finca. Cada elemento contiene:

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `id` | integer | Identificador. |
| `user` | integer o `null` | Identificador del usuario relacionado. |
| `farm_id` | integer o `null` | Identificador de la finca relacionada. |
| `description` | string | Descripción del cambio. |
| `type_source` | string | Tipo de entidad que originó el registro. |
| `source_id` | integer o `null` | Identificador de la entidad de origen. |
| `ip` | string o `null` | Dirección IP registrada. |
| `old_values` | object o `null` | Valores previos, si están disponibles. |
| `new_values` | object o `null` | Valores nuevos, si están disponibles. |
| `created_at` | fecha/hora | Fecha de creación. |

`type_source` puede ser: `User`, `UserFarm`, `Farm`, `FarmRole`, `Pond`,
`UserFarmPond`, `TypeProduct`, `Product`, `PurchaseDetail`, `Supplier`,
`Specie`, `SpecieParameter`, `SpecieFeedingReference`,
`SpecieProductionReference`, `Batch`, `ProductionPlan`, `Cycle`,
`FeedingSchedule`, `FeedingPlan`, `FeedingEvent`, `DailyStat`,
`ProductUsageLog`, `ControlStat`, `FishEvaluated`, `HealthStat`,
`TreatmentPlan`, `TreatmentEvent`, `AmbientalMeasurement`, `Alert`, `Sale`,
`InventoryMovement`, `Harvest`, `HarvestClassification`, `Client`, `Buy`,
`Invitation`, `BatchTransfer`, `GradingEvent`, `SaleDetail`,
`CyclePondBatch`, `PondBatch`, `SpeciePondType` o `ProductionReport`.

AuditLog solo permite `GET` de lista y detalle; no acepta creación,
actualización ni eliminación.
