# Guía de campos del registro de auditoría

## Alcance del endpoint

El endpoint de lista es:

```text
GET /api/farms/core/{farm_id}/auditlogs/
```

El detalle de un registro es:

```text
GET /api/farms/core/{farm_id}/auditlogs/{id}/
```

Se requiere autenticación y permiso `audit_logs.view` para la finca. La lista
está paginada (50 registros por página) y admite filtros combinables por fecha
(`date_from`, `date_to`), origen
(`origin`, `origin_id`), usuario (`user`) e IP (`ip`). Los detalles del
contrato están en la [guía de filtros](./auditlog-filters-implementation.md).
Una respuesta de lista tiene la forma:

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 301,
      "user": 27,
      "user_name": "Ana Pérez",
      "farm_id": 8,
      "description": "FarmRole 12 updated",
      "type_source": "FarmRole",
      "source_id": 12,
      "ip": "192.0.2.10",
      "old_values": {"name": "Operador"},
      "new_values": {"name": "Encargado"},
      "created_at": "2026-11-07T18:20:00Z"
    }
  ]
}
```

La respuesta de detalle es un objeto con los mismos campos que cada elemento
de `results`. Los tipos de campo y ejemplos de abajo describen el contrato
actual del backend. Los ejemplos son ilustrativos.

## Campos de paginación

| Nombre | Tipo | Descripción | Origen | Ejemplo | Notas |
| --- | --- | --- | --- | --- | --- |
| `count` | integer | Cantidad de registros que coinciden con la consulta. | Paginador de DRF sobre `audit_log`. | `124` | Es el total, no la cantidad de elementos de la página. |
| `next` | string o `null` | URL de la siguiente página. | Paginador de DRF. | `"/api/farms/core/8/auditlogs/?page=2"` | `null` cuando no hay página siguiente. |
| `previous` | string o `null` | URL de la página anterior. | Paginador de DRF. | `null` | `null` en la primera página. |
| `results` | array de objetos | Registros de auditoría de la página actual. | Consulta de `AuditLog` filtrada por finca. | `[{"id": 301, "...": "..."}]` | Cada objeto contiene los campos descritos a continuación. |

## Campos de cada registro

### `id`

- **Tipo:** integer.
- **Descripción:** Identificador único del registro de auditoría.
- **Uso:** Identificar el evento y solicitar su detalle.
- **Origen:** `audit_log.id` (`AuditLog.id`).
- **Ejemplo:** `301`.
- **Notas:** No es el identificador de la entidad modificada; ese valor es
  actualmente `source_id`.

### `user`

- **Tipo:** integer o `null`.
- **Descripción:** ID de la cuenta que ejecutó la acción.
- **Uso:** Referencia técnica del actor; no mostrar el número como nombre.
- **Origen:** `audit_log.user_id`, clave foránea opcional a `accounts.User`
  (`user.id`).
- **Ejemplo:** `27`.
- **Notas:** Puede ser `null` si el cambio no tuvo una solicitud asociada o no
  fue posible identificar al usuario. Para mostrar una persona, usar
  `user_name`.

### `user_name`

- **Tipo:** string o `null`.
- **Descripción:** Nombre completo del actor; si nombre y apellido están
  vacíos, se usa su correo.
- **Uso:** Etiqueta legible de quién realizó el cambio.
- **Origen:** Campo calculado desde `User.name`, `User.lastname` y, como
  alternativa, `User.email`. No es una columna de `audit_log`.
- **Ejemplo:** `"Ana Pérez"`.
- **Notas:** Es un valor calculado al leer el registro. Si el usuario cambia su
  nombre o correo, la respuesta histórica mostrará el dato actual, no una copia
  inmutable del nombre que tenía al realizar la acción. En la propuesta de
  `detail` se recomienda guardar también una instantánea del actor.

### `farm_id`

- **Tipo:** integer o `null`.
- **Descripción:** Identificador de la finca a la que corresponde el evento.
- **Uso:** Contexto de finca y aislamiento de los registros.
- **Origen:** `audit_log.farm_id` (integer, no es una clave foránea).
- **Ejemplo:** `8`.
- **Notas:** El endpoint de lista filtra por la finca de la ruta, por lo que no
  debe incluir eventos de otras fincas. Puede ser `null` en eventos no
  asociados a una finca.

### `description`

- **Tipo:** string.
- **Descripción actual:** Texto breve generado al guardar el evento. Para los
  cambios registrados por señales suele tener el formato
  `"{Entidad} {id} {operación}"`, por ejemplo `"FarmRole 12 updated"`.
- **Uso:** Resumen de una línea en la lista de auditoría.
- **Origen:** `audit_log.description`; normalmente se genera en
  `apps/core/signals.py` a partir del nombre de clase, ID y acción. Algunos
  flujos especiales escriben una descripción propia.
- **Ejemplo actual:** `"FarmRole 12 updated"`.
- **Notas:** El texto actual suele estar en inglés y presenta el ID técnico.
  No siempre explica el objeto afectado ni el cambio concreto. La mejora
  recomendada se especifica en [Mejoras recomendadas](#mejoras-recomendadas-del-payload).

### `type_source`

- **Tipo:** string.
- **Descripción:** Tipo de entidad cuyo cambio produjo el evento.
- **Uso:** Clasificar la acción y determinar el tipo del objeto de origen.
- **Origen:** `audit_log.type_source`; normalmente es el nombre de clase del
  modelo, obtenido en `apps/core/signals.py`.
- **Ejemplo:** `"FarmRole"`.
- **Notas:** Es una etiqueta interna en inglés y puede ser poco descriptiva
  para una interfaz. Mantener el valor técnico para compatibilidad; mostrar en
  la interfaz un nombre localizado, por ejemplo `"Rol de finca"`.

### `source_id`

- **Tipo:** integer o `null`.
- **Descripción:** ID de la instancia que cambió.
- **Uso actual:** Junto con `type_source`, permite identificar el modelo y su
  clave primaria.
- **Origen:** `audit_log.source_id`; el registro del evento copia la PK de la
  instancia observada por la señal.
- **Ejemplo:** `12`.
- **Notas:** Es una referencia polimórfica: el ID solo no indica qué entidad
  representa ni cómo llegar a ella. Puede ser `null` o apuntar a una instancia
  eliminada. Para la interfaz se recomienda sustituir este campo en una nueva
  versión del contrato por `origin`, descrito más abajo.

### `ip`

- **Tipo:** string o `null`.
- **Descripción:** Dirección IP observada para la solicitud que generó el
  evento.
- **Uso:** Contexto de auditoría y revisión administrativa.
- **Origen:** `audit_log.ip`; `apps/core/signals.py` toma la primera IP de
  `X-Forwarded-For` cuando está presente, o `REMOTE_ADDR` en otro caso.
- **Ejemplo:** `"192.0.2.10"`.
- **Notas:** Puede ser `null` para tareas programadas o cambios ejecutados sin
  una solicitud HTTP. La confianza en `X-Forwarded-For` depende de que el
  proxy confiable de la infraestructura lo establezca correctamente. No usarlo
  como ubicación precisa de una persona.

### `old_values`

- **Tipo:** object JSON o `null`.
- **Descripción:** Instantánea de los campos concretos de la entidad antes
  del cambio.
- **Uso:** Comparar el estado anterior con el nuevo en el detalle del evento.
- **Origen:** `audit_log.old_values`, calculado por `_snapshot()` en
  `apps/core/signals.py` leyendo los campos del modelo.
- **Ejemplo:** `{"name": "Operador"}`.
- **Notas:** Es posible que sea `null` en una creación o cuando la instancia
  previa no se pudo obtener. Se excluyen `password` y `last_login`; otras
  claves foráneas suelen aparecer como IDs y pueden no ser comprensibles sin
  resolución adicional. No se debe mostrar el JSON sin formato a usuarios
  finales.

### `new_values`

- **Tipo:** object JSON o `null`.
- **Descripción:** Instantánea de los campos concretos de la entidad después
  del cambio.
- **Uso:** Comparar el nuevo estado con el anterior.
- **Origen:** `audit_log.new_values`, calculado por `_snapshot()` y serializado
  como JSON. En una eliminación se almacena `null`.
- **Ejemplo:** `{"name": "Encargado"}`.
- **Notas:** En una creación contiene el estado creado; en una actualización,
  el estado posterior; en una eliminación, `null`. Los campos relacionados
  pueden ser IDs. Conviene presentar diferencias campo por campo con etiquetas
  traducidas y valores relacionados resueltos.

### `created_at`

- **Tipo:** string de fecha y hora ISO 8601.
- **Descripción:** Momento en que se guardó el evento de auditoría.
- **Uso:** Orden cronológico y presentación de fecha/hora local.
- **Origen:** `audit_log.created_at`, asignado por `auto_now_add=True`.
- **Ejemplo:** `"2026-11-07T18:20:00Z"`.
- **Notas:** El backend almacena fechas con zona horaria. La interfaz debe
  convertirlas a la zona horaria configurada para la persona y conservar el
  instante original.

## `detail`: situación actual y propuesta

`detail` **no es un campo del contrato actual** de este endpoint. El backend
devuelve `old_values` y `new_values` como objetos JSON; no devuelve un campo
llamado `detail` ni una explicación completa en lenguaje natural.

Se recomienda agregar `detail` en una nueva versión como objeto estructurado,
sin reemplazar la evidencia técnica almacenada:

```json
{
  "detail": {
    "summary": "Ana Pérez cambió el rol «Operador» a «Encargado» en la finca «El Remanso».",
    "actor": {
      "id": 27,
      "name": "Ana Pérez"
    },
    "target": {
      "type": "FarmRole",
      "name": "Encargado",
      "id": 12
    },
    "changes": [
      {
        "field": "name",
        "label": "Nombre",
        "before": "Operador",
        "after": "Encargado"
      }
    ],
    "occurred_at": "2026-11-07T18:20:00Z"
  }
}
```

- **Resumen visible (`detail.summary`):** `"Ana Pérez cambió el rol «Operador» a «Encargado» en la finca «El Remanso»."`
- **Backend:** producir actor/objetivo estables y un conjunto de cambios
  seguro, además del resumen localizado o de claves de evento y parámetros.
- **Frontend:** mostrar el resumen y cambios con etiquetas amigables; conservar
  un panel opcional de información técnica para soporte.
- **Contrato:** nuevo campo aditivo `detail`; los consumidores actuales pueden
  ignorarlo. Las etiquetas técnicas y el JSON histórico continúan disponibles
  durante la transición.
- **Caveat:** el resumen debe generarse con plantillas controladas y valores
  escapados. No interpolar HTML ni confiar en textos arbitrarios de usuario.

## Mejoras recomendadas del payload

### `origin`: referencia vinculada y vista previa del objeto

**Estado actual:** el backend devuelve `type_source` y `source_id` separados.
Con esos valores se conoce el tipo interno y la PK, pero la respuesta no
incluye el nombre legible, un destino de navegación ni una vista previa
compacta. El frontend no puede resolverlo de forma general con fiabilidad:
los modelos tienen rutas distintas, algunos objetos podrían haberse eliminado
y ciertas referencias requieren IDs de finca, estanque, ciclo u otros padres.

**Contrato propuesto:**

```json
{
  "origin": {
    "id": 12,
    "name": "Encargado",
    "type": {
      "code": "FarmRole",
      "label": "Rol de finca"
    },
    "url": "/api/farms/8/roles/12/",
    "preview": {
      "title": "Encargado",
      "subtitle": "Rol de la finca El Remanso",
      "fields": [
        {"label": "Nombre", "value": "Encargado"},
        {"label": "Finca", "value": "El Remanso"}
      ]
    }
  }
}
```

Cuando el objeto ya no exista, la referencia debe permanecer útil y explícita:

```json
{
  "origin": {
    "id": 12,
    "name": "Rol eliminado",
    "type": {
      "code": "FarmRole",
      "label": "Rol de finca"
    },
    "url": null,
    "preview": null
  }
}
```

- **Backend:** resolver la entidad con `type_source` + `source_id`, comprobar
  que pertenece a la finca del evento, y agregar nombre, tipo localizado,
  URL canónica y una vista previa con campos permitidos. Si se eliminó, no
  devolver error ni una entidad ajena: responder con `url: null` y `preview:
  null`. Definir una tabla de resolución por tipo de entidad/ruta, ya que las
  rutas actuales no comparten una convención universal.
- **Endpoint/consulta:** enriquecer el serializer de auditoría y cargar los
  orígenes en lote para los 50 resultados (no hacer una consulta adicional
  por cada fila). La consulta debe aplicar el mismo aislamiento por finca que
  el endpoint de auditoría. El `select_related("user")` actual no carga ni
  resuelve el objeto de origen.
- **Frontend:** presentar `origin.name` como texto principal y
  `origin.type.label` como tipo. Si `origin.url` no es `null`, mostrar un enlace
  o botón para abrir el elemento y un panel compacto usando `origin.preview`.
  Si no hay destino, mostrar la vista previa disponible y el texto
  **«Elemento no disponible»**. Usar etiquetas como **«Origen»**,
  **«Ver elemento»** y **«Vista previa»**.
- **Contrato:** cambio aditivo recomendado en primera instancia: agregar
  `origin` y conservar `source_id` temporalmente como campo obsoleto para
  clientes existentes. En una versión mayor, eliminar `source_id`; la
  interfaz nueva debe consumir `origin.id` en lugar del campo plano. Mantener
  `type_source` durante la transición para facilitar compatibilidad y soporte.
- **Seguridad:** nunca convertir directamente un ID recibido en una URL
  arbitraria. El backend debe construir las rutas desde una lista controlada
  de tipos y rutas, escapar/validar sus parámetros y confirmar el ámbito de
  finca antes de incluir datos del objeto.
- **Límite importante:** el backend no conoce las rutas internas de navegación
  del frontend. `origin.url` debe ser una ruta API canónica para consultar el
  objeto; el frontend debe mapear el tipo permitido a su propia pantalla y
  usar la API para resolver los datos. No mostrar un enlace a una ruta API
  como si fuera automáticamente una página web.

### `description`: resumen de acción claro y en español

**Comportamiento actual:** generalmente se genera como `"{clase} {id}
{operación}"`. Es una descripción técnica; puede estar en inglés y no suele
decir quién hizo el cambio ni mostrar los valores modificados.

| Antes | Después (propuesta en español) |
| --- | --- |
| `"FarmRole 12 updated"` | `"Ana Pérez actualizó el rol «Operador» de la finca «El Remanso»."` |
| `"UserFarm 27 created"` | `"Carlos Díaz agregó a Ana Pérez a la finca «El Remanso»."` |
| `"Product 43 deleted"` | `"Ana Pérez eliminó el producto «Alimento de engorde» de la finca «El Remanso»."` |

- **Backend:** registrar un código de evento estable (por ejemplo,
  `farm_role.updated`) y contexto estructurado: actor, objeto, finca, acción y
  diferencias seguras. Producir una frase base consistente en español o
  devolver clave + parámetros para localización. No inferir el verbo solo del
  nombre de la clase.
- **Frontend:** presentar la frase en español; si el backend entrega claves,
  mantener el catálogo de traducciones y escapar los valores interpolados.
- **Contrato:** propuesta aditiva; conservar temporalmente `description` como
  texto legado y usar `detail.summary` como texto preferido. El formato actual
  puede seguir existiendo para clientes previos hasta retirar la versión
  antigua.
- **Caveat:** algunas operaciones usan descripciones personalizadas. La
  migración debe estandarizar esos productores para que la experiencia sea
  uniforme.

### `old_values` y `new_values`: diferencias legibles

- **Backend:** agregar a `detail.changes` una lista curada de cambios con
  nombre de campo localizado y valores anteriores/nuevos. Resolver relaciones
  conocidas (por ejemplo, ID de finca a nombre de finca) al crear el detalle.
  Omitir secretos y campos internos.
- **Frontend:** renderizar los cambios como pares **«Antes»** y **«Después»**,
  con etiquetas en español; no presentar claves técnicas ni el JSON crudo en
  la vista normal.
- **Contrato:** `old_values` y `new_values` se conservan para soporte y
  compatibilidad. `detail.changes` es la representación recomendada para la
  interfaz.
- **Caveat:** restringir campos visibles por tipo de entidad; no exponer
  contraseñas, tokens, datos privados innecesarios ni valores internos
  directamente.

## Resumen de trabajo recomendado

| Cambio | Backend | Frontend | Cambio de contrato |
| --- | --- | --- | --- |
| Referencia `origin` | Resolver entidad, validar ámbito de finca y producir nombre, etiqueta, URL API canónica y vista previa en lote. | Mostrar nombre, tipo, enlace a la pantalla correcta y vista previa; mostrar **«Elemento no disponible»** si fue eliminado. | Agregar `origin`; conservar `source_id` deprecado durante la transición y quitarlo en una versión mayor. |
| Descripción de acción | Estandarizar tipos de evento y contexto; generar resumen en español o clave y parámetros. | Mostrar texto claro y localizar/escapar valores si recibe claves. | Agregar `detail.summary`; mantener `description` temporalmente. |
| Detalle de cambios | Construir `detail.actor`, `detail.target`, `detail.changes` y `detail.occurred_at` con datos seguros. | Presentar actor, objetivo, hora y cambios **«Antes» / «Después»** en español. | Agregar `detail` de forma aditiva; mantener `old_values` y `new_values` como campos técnicos durante la transición. |
| Campos técnicos | Mantener IDs y JSON para integración/soporte, evitando filtraciones. | No usar IDs como etiqueta principal ni mostrar JSON crudo en la vista normal. | Preservar campos actuales hasta una versión mayor documentada. |

> **Estado del contrato:** esta guía documenta los campos actualmente
> devueltos y propone los nuevos campos. `origin` y `detail` son propuestas y
> no forman parte del contrato implementado hasta que se realicen los cambios
> de backend y frontend descritos arriba.
