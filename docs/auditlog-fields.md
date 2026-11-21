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
      "user_name": "Keyler Sneider Arias Calvo",
      "farm_id": 8,
      "description": "Keyler Sneider Arias Calvo retiró el rol «Administrador» de Roger Santiago Miranda Hoyos en la finca «El Remanso».",
      "type_source": "UserFarm",
      "source_id": 43,
      "ip": "192.0.2.10",
      "old_values": {
        "id": 43,
        "user_id": 91,
        "farm_id": 8,
        "farm_role_id": 12,
        "status": "active",
        "is_owner": false,
        "display": {
          "fields": {
            "id": {"label": "Id", "value": 43},
            "user_id": {"label": "Usuario", "value": {"id": 91, "nombre": "Roger Santiago Miranda Hoyos"}},
            "farm_id": {"label": "Finca", "value": {"id": 8, "nombre": "El Remanso"}},
            "farm_role_id": {"label": "Rol", "value": {"id": 12, "nombre": "Administrador"}},
            "status": {"label": "Estado", "value": "Trabaja actualmente"},
            "is_owner": {"label": "Propietario", "value": "No"}
          },
          "summary": "Roger Santiago Miranda Hoyos tenía asignado el rol «Administrador» en la finca «El Remanso»."
        }
      },
      "new_values": {
        "id": 43,
        "user_id": 91,
        "farm_id": 8,
        "farm_role_id": null,
        "status": "active",
        "is_owner": false,
        "display": {
          "fields": {
            "id": {"label": "Id", "value": 43},
            "user_id": {"label": "Usuario", "value": {"id": 91, "nombre": "Roger Santiago Miranda Hoyos"}},
            "farm_id": {"label": "Finca", "value": {"id": 8, "nombre": "El Remanso"}},
            "farm_role_id": {"label": "Rol", "value": null},
            "status": {"label": "Estado", "value": "Trabaja actualmente"},
            "is_owner": {"label": "Propietario", "value": "No"}
          },
          "summary": "Roger Santiago Miranda Hoyos no tiene un rol asignado en la finca «El Remanso»."
        }
      },
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
- **Descripción actual:** Texto generado al guardar el evento. Las nuevas
  entradas de las señales están en español e incluyen actor, acción, objetivo
  con nombre y finca cuando aplica. Por ejemplo:
  `"Keyler Sneider Arias Calvo retiró el rol «Administrador» de Roger Santiago Miranda Hoyos en la finca «El Remanso»."`
- **Uso:** Resumen de una línea en la lista de auditoría.
- **Origen:** `audit_log.description`, generado por `apps/core/signals.py`.
  Algunos flujos de auditoría especializados conservan su propio texto.
- **Notas:** Las entradas anteriores no se reescriben y pueden seguir usando
  el formato técnico en inglés. La descripción de cada evento nuevo queda
  guardada como texto histórico y no cambia si luego se renombra una persona o
  entidad.

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
  previa no se pudo obtener. En los eventos nuevos conserva las claves y
  valores técnicos existentes y añade `display`, con etiquetas, referencias
  legibles y resumen en español. Se excluyen `password` y `last_login`. Para
  la interfaz usar `old_values.display.summary` y
  `old_values.display.fields`, no mostrar el JSON crudo.

### `new_values`

- **Tipo:** object JSON o `null`.
- **Descripción:** Instantánea de los campos concretos de la entidad después
  del cambio.
- **Uso:** Comparar el nuevo estado con el anterior.
- **Origen:** `audit_log.new_values`, calculado por `_snapshot()` y serializado
  como JSON. En una eliminación se almacena `null`.
- **Ejemplo:** `{"name": "Encargado"}`.
- **Notas:** En una creación contiene el estado creado; en una actualización,
  el estado posterior; en una eliminación, `null`. Conserva los valores
  técnicos previos y agrega `display` con las etiquetas y nombres que la
  interfaz necesita sin hacer peticiones extra. Usar
  `new_values.display.summary` y `new_values.display.fields`.

### `old_values.display` y `new_values.display`

Estos objetos se agregan en los eventos generados por las señales a partir de
este cambio. Las claves técnicas de `old_values` y `new_values` se mantienen
para compatibilidad.

```json
{
  "farm_role_id": 12,
  "display": {
    "fields": {
      "farm_role_id": {
        "label": "Rol",
        "value": {"id": 12, "nombre": "Administrador"}
      },
      "status": {
        "label": "Estado",
        "value": "Trabaja actualmente"
      }
    },
    "summary": "Roger Santiago Miranda Hoyos tenía asignado el rol «Administrador» en la finca «El Remanso»."
  }
}
```

- `fields`: representación legible de cada campo. La clave coincide con el
  nombre técnico para facilitar la comparación; `label` es el nombre para la
  interfaz. Para relaciones `value` tiene `{ "id", "nombre" }`; para opciones
  y booleanos se usan etiquetas como `"Trabaja actualmente"` y `"Sí"`/`"No"`.
- `summary`: frase breve en español. En un cambio de rol de membresía, el
  valor anterior usa pasado (`tenía asignado`) y el nuevo describe el estado
  resultante (`tiene asignado` o `no tiene un rol asignado`).
- Este campo anidado no se calcula retroactivamente: las entradas existentes
  antes del despliegue no tendrán `display`. La interfaz debe tolerar su
  ausencia y recurrir a los valores técnicos para esos registros antiguos.

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

**Implementado para eventos nuevos generados por señales:** se genera una
frase en español con actor, acción, objetivo y finca cuando aplica.

| Antes | Ahora |
| --- | --- |
| `"UserFarm 43 updated"` | `"Keyler Sneider Arias Calvo retiró el rol «Administrador» de Roger Santiago Miranda Hoyos en la finca «El Remanso»."` |
| `"FarmRole 12 updated"` | `"Ana Pérez actualizó el rol de finca «Operador» de la finca «El Remanso»."` |

- **Backend:** la generación común está implementada en `apps/core/signals.py`.
  Hay textos especializados para cambios de membresía y permisos de rol; los
  demás tipos de entidad usan un nombre localizado, un nombre/código legible
  y el contexto de finca cuando se puede determinar.
- **Frontend:** mostrar `description` directamente como resumen principal.
  Los valores interpolados son texto; renderizarlos escapados, nunca como
  HTML.
- **Contrato:** no cambia el tipo ni el nombre del campo. Los eventos antiguos
  y algunos flujos especializados pueden conservar descripciones anteriores.

### `old_values` y `new_values`: diferencias legibles

- **Backend:** en eventos nuevos, ambos snapshots conservan los valores
  técnicos actuales y agregan `display.fields` con etiquetas y relaciones
  legibles, además de `display.summary`. El caso de cambio/eliminación de rol
  en una membresía identifica al usuario objetivo y el rol anterior/nuevo.
- **Frontend:** presentar `display.summary` como texto destacado y
  `display.fields` como diferencias **«Antes» / «Después»**. Usar `label` y
  `value`; no mostrar claves técnicas ni el JSON crudo. Si `display` no existe
  (evento anterior o flujo especializado), usar un fallback genérico sin
  efectuar peticiones automáticas por cada ID.
- **Contrato:** cambio aditivo en el contenido de los JSON existentes; los
  campos previos y sus claves no se eliminan. No requiere migración de base de
  datos. Algunas entradas preexistentes no tienen la información nueva.
- **Privacidad:** se mantienen excluidos `password` y `last_login`; no mostrar
  valores técnicos de los snapshots como texto final sin revisar el tipo de
  entidad.

## Resumen de trabajo recomendado

| Cambio | Backend | Frontend | Cambio de contrato |
| --- | --- | --- | --- |
| Referencia `origin` | Pendiente: resolver entidad, validar ámbito de finca y producir nombre, URL API y vista previa en lote. | Pendiente: mostrar nombre, tipo, enlace y vista previa. | Sigue siendo propuesta; hoy se mantienen `type_source` y `source_id`. |
| Descripción de acción | Implementado en señales comunes con actor, acción, objetivo legible y finca cuando aplica. | Mostrar `description` directamente y escapar como texto. | Mismo campo `description`; las entradas históricas no se reescriben. |
| Diferencias anterior/nuevo | Implementado: snapshots nuevos agregan `display.fields` y `display.summary`, conservando las claves técnicas. | Mostrar el resumen y las parejas «Antes» / «Después»; tolerar que entradas antiguas no tengan `display`. | Aditivo dentro de `old_values` y `new_values`; sin migración. |
| `detail` estructurado | Propuesta futura para actor/objetivo/cambios normalizados. | Propuesta futura. | No forma parte de la respuesta actual. |

> **Estado del contrato:** `description` y la sección `display` de snapshots
> están implementados en el backend para eventos nuevos generados por señales.
> `origin` y `detail` siguen siendo propuestas no implementadas.
