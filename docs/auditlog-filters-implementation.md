# Filtros del registro de auditoría

## Estado

Los filtros descritos aquí están implementados en:

```text
GET /api/farms/core/{farm_id}/auditlogs/
```

La respuesta mantiene la paginación existente de 50 registros por página. Los
filtros pueden combinarse; el servidor aplica una condición `AND` entre los
parámetros enviados. La consulta siempre queda limitada a la finca de la ruta.

## Parámetros disponibles

| Parámetro | Formato | Comportamiento |
| --- | --- | --- |
| `date_from` | `YYYY-MM-DD` | Incluye eventos desde el inicio de esta fecha. |
| `date_to` | `YYYY-MM-DD` | Incluye eventos hasta el final de esta fecha. |
| `origin` | Valor de `type_source` | Filtra por tipo de entidad que originó el cambio; por ejemplo `FarmRole`, `Product` o `UserFarm`. |
| `origin_id` | Entero positivo | Filtra por ID de la entidad origen (`source_id`). Puede combinarse con `origin` para distinguir IDs de diferentes tipos. |
| `user` | ID, nombre/apellido o correo | Un valor numérico busca el ID exacto. En otro caso, busca términos sin distinguir mayúsculas en nombre, apellido o correo. |
| `ip` | IPv4 o IPv6 | Coincidencia exacta con la dirección IP registrada. |
| `page` | Entero positivo | Página que se solicita; pertenece al paginador actual. |

`date_from` y `date_to` son inclusivas. Si se envían ambas, `date_from` debe
ser igual o anterior a `date_to`. Las fechas se interpretan desde la medianoche
local configurada en Django; el límite superior se implementa como el inicio
del día siguiente, por lo que también incluye registros con fracciones de
segundo del último día.

Los parámetros de filtro enviados con valor vacío (`date_from=`, `origin=`,
etc.) se ignoran, igual que si no se hubieran enviado. Esto permite enviar
directamente los valores de controles de formulario vacíos; los espacios en
blanco no se consideran vacíos y siguen sujetos a validación.

Los valores admitidos para `origin` corresponden a `type_source`:
`User`, `UserFarm`, `Farm`, `FarmRole`, `FarmRoleAppPermission`, `Pond`,
`UserFarmPond`, `TypeProduct`, `Product`, `PurchaseDetail`, `Supplier`,
`Specie`, `SpecieParameter`, `SpecieFeedingReference`,
`SpecieProductionReference`, `Batch`, `ProductionPlan`, `Cycle`,
`FeedingSchedule`, `FeedingPlan`, `FeedingEvent`, `DailyStat`,
`ProductUsageLog`, `ControlStat`, `FishEvaluated`, `HealthStat`,
`TreatmentPlan`, `TreatmentEvent`, `AmbientalMeasurement`, `Alert`, `Sale`,
`InventoryMovement`, `Harvest`, `HarvestClassification`, `Client`, `Buy`,
`Invitation`, `BatchTransfer`, `GradingEvent`, `SaleDetail`,
`CyclePondBatch`, `PondBatch`, `SpeciePondType` y `ProductionReport`.

## Ejemplos para frontend

### Filtrar por rango de fechas

```http
GET /api/farms/core/8/auditlogs/?date_from=2026-11-01&date_to=2026-11-07
```

### Filtrar por tipo e ID de origen

```http
GET /api/farms/core/8/auditlogs/?origin=FarmRole&origin_id=12
```

`origin` usa valores técnicos actuales de `type_source`; para mostrarlos, la
interfaz debe convertirlos a etiquetas en español. Ejemplos de etiquetas:
`FarmRole` → **Rol de finca**, `Product` → **Producto** y `UserFarm` →
**Membresía de finca**.

### Buscar por usuario

```http
GET /api/farms/core/8/auditlogs/?user=27
GET /api/farms/core/8/auditlogs/?user=ana
GET /api/farms/core/8/auditlogs/?user=ana%20perez
```

La búsqueda textual no distingue mayúsculas y requiere que cada término
coincida con el nombre, apellido o correo. Si el usuario no tiene nombre, se
puede buscar por su correo. `user_name` en cada resultado continúa siendo el
texto recomendado para mostrar el actor.

### Filtrar por IP y combinar condiciones

```http
GET /api/farms/core/8/auditlogs/?ip=192.0.2.10&origin=FarmRole&user=ana
```

### Navegar páginas con filtros persistentes

```http
GET /api/farms/core/8/auditlogs/?origin=FarmRole&date_from=2026-11-01&page=2
```

El paginador devuelve `next` y `previous`; la interfaz puede seguir esas URL
para conservar automáticamente los filtros y no necesita reconstruirlos.

## Validación y errores

Los parámetros inválidos devuelven `400 Bad Request` con errores por campo:

```json
{
  "date_from": ["Formato de fecha inválido. Use YYYY-MM-DD."]
}
```

También se rechazan tipos `origin` desconocidos, `origin_id` no positivo,
direcciones IP inválidas y rangos donde `date_from` sea posterior a `date_to`.
Los demás parámetros válidos de una misma solicitud no desactivan la
validación.

## Implementación técnica realizada

### Backend

- `AuditLogFilterSerializer` valida fechas, tipo de origen, ID de origen,
  usuario e IP.
- `AuditLogView.get_queryset()` aplica cada filtro al queryset de la finca
  antes de la paginación.
- El filtro `user` acepta ID exacto o búsqueda parcial de nombre/apellido/
  correo. Cuando se buscan varios términos, todos deben coincidir en alguno
  de esos campos.
- Las fechas se convierten en límites de fecha/hora conscientes de zona
  horaria: desde el inicio de `date_from` hasta, sin incluir, la medianoche
  del día posterior a `date_to`.
- Todos los filtros se combinan con `AND`; la búsqueda de usuario combina
  nombre, apellido y correo con `OR`.

### Frontend

1. Añadir controles de fecha inicial y final.
2. Ofrecer un selector de origen con etiquetas visibles en español y enviar
   como valor el código exacto de `type_source`.
3. Ofrecer búsqueda de usuario por ID, nombre, apellido o correo. Mostrar el
   nombre legible (`user_name`) en las filas; el ID solo se necesita si el
   operador lo ingresa explícitamente.
4. Validar visualmente el rango de fechas, pero tratar el `400` del servidor
   como autoridad y mostrar un mensaje en español, por ejemplo:
   **«La fecha inicial debe ser anterior o igual a la fecha final.»**
5. Construir los parámetros con `URLSearchParams` para codificar espacios y
   mantenerlos junto al número de página. Los controles vacíos se pueden
   omitir o enviar como cadenas vacías; el servidor los ignora. Al cambiar
   un filtro, volver a `page=1`.
6. Usar `next`/`previous` de la respuesta para paginar. `count` refleja el
   total tras aplicar todos los filtros.

No se requieren migraciones de base de datos ni cambios en la forma de cada
registro. La respuesta mantiene `count`, `next`, `previous`, `results` y los
campos del auditlog ya documentados en
[auditlog-fields.md](./auditlog-fields.md).
