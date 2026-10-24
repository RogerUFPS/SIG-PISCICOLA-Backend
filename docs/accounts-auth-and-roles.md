## Roles y permisos de operarios por granja

Los tipos globales de cuenta siguen siendo `Admin`, `Productor` y `Operario`.
Los roles que se configuran en esta sección son perfiles de trabajo locales a
una granja; no crean nuevos tipos globales de usuario. El productor propietario
administra los roles y asigna cada rol a los operarios de esa granja.

### `GET /api/farms/<farm_id>/roles/apps/`

Lista las aplicaciones disponibles para configurar permisos de la finca,
incluyendo `core_alerts` y `core_auditlogs` como permisos independientes.

Cada elemento contiene la clave `app` (para enviar en permisos) y un nombre
visible `name`.

### `GET /api/farms/<farm_id>/roles/`

Lista los roles activos de esa granja. Cada rol incluye su nombre, los permisos
heredados del sistema anterior y `app_permissions`, con esta forma:

| Campo | Tipo | Significado |
| --- | --- | --- |
| `app` | string | Clave de app obtenida de `/roles/apps/`. |
| `can_view` | boolean | Puede consultar/leer. |
| `can_create` | boolean | Puede crear. |
| `can_edit` | boolean | Puede actualizar. |
| `can_delete` | boolean | Puede eliminar. |

### `POST /api/farms/<farm_id>/roles/`

Crea un rol dentro de la granja indicada:

```json
{
  "name": "Encargado sanitario",
  "app_permissions": [
    {
      "app": "health",
      "can_view": true,
      "can_create": true,
      "can_edit": true,
      "can_delete": false
    },
    {
      "app": "monitoring",
      "can_view": true,
      "can_create": false,
      "can_edit": false,
      "can_delete": false
    }
  ]
}
```

Los permisos quedan asociados al rol y, por tanto, a esa granja solamente. Las
apps deben pertenecer al listado de `/roles/apps/`, no se pueden repetir y
`can_view` debe ser `true` si cualquiera de las otras acciones está habilitada.
`core_alerts` y `core_auditlogs` solo aceptan `can_view`; son permisos
independientes. Si no se envía `app_permissions`, el rol nuevo queda sin
permisos por app.

### `GET /api/farms/<farm_id>/roles/<role_id>/`

Obtiene un rol y sus permisos para una granja.

### `PUT /api/farms/<farm_id>/roles/<role_id>/` y
`PATCH /api/farms/<farm_id>/roles/<role_id>/`

Actualiza el rol. Si se incluye `app_permissions`, la lista reemplaza los
permisos previos del rol; si se omite, estos no cambian. Envía una lista vacía
para revocar todos los permisos por app.

Las autorizaciones consultan el rol y sus permisos en cada solicitud. Por
ello, los cambios afectan también a operarios con una sesión ya iniciada.
Al cambiar los permisos `permissions` de un rol, se actualizan los permisos de
los miembros asignados a ese rol. Al eliminar un rol, sus miembros quedan sin
rol ni permisos copiados de ese rol.

### `DELETE /api/farms/<farm_id>/roles/<role_id>/`

Desactiva el rol de esa granja. Sus permisos dejan de autorizar operaciones.

### Asignar un rol a un operario

Usa el endpoint de miembros de la granja para asignar `farm_role`:

`PATCH /api/farms/<farm_id>/members/<user_id>/`

```json
{
  "farm_role": 12
}
```

El rol debe pertenecer a la misma granja. Para retirar la asignación, envía
`{"farm_role": null}`. Las asignaciones y permisos de otros productores o
granjas no se modifican.

### Administrar miembros

#### `GET /api/farms/<farm_id>/members/`

Lista los miembros de la finca. Cada elemento contiene `user` (resumen del
usuario), `farm`, `farm_role`, `permissions`, `status` e `is_owner`.

#### `GET /api/farms/<farm_id>/members/<user_id>/`

Obtiene la membresía del usuario indicado. La respuesta contiene los mismos
campos que cada elemento de la lista.

#### `PATCH /api/farms/<farm_id>/members/<user_id>/`

Actualiza el estado de un miembro con `{"status": "active"}` o
`{"status": "inactive"}`. Solo el propietario puede asignar `farm_role` y
`permissions`; `farm_role` acepta el ID de un rol de la misma finca o `null`.
`permissions` acepta las opciones descritas abajo. `user`, `user_id`, `farm` e
`is_owner` no son modificables. Un usuario con `MANAGE_USERS` puede cambiar el
estado o retirar a otros miembros, pero no puede cambiar el propietario ni
asignar roles o permisos.

#### `DELETE /api/farms/<farm_id>/members/<user_id>/`

Retira al miembro indicado de la finca. No permite retirar al propietario.

### Invitar usuarios a una finca

#### `POST /api/invitations/operario/`

Envía una invitación a una finca. Si la cuenta ya existe, debe aceptar la
invitación para incorporarse:

```json
{
  "email": "operario@example.com",
  "farm_id": 12
}
```

Se necesita `MANAGE_USERS` en la finca indicada o ser su propietario. El
permiso no concede acceso a las demás fincas.

#### `GET /api/invitations/?farm_id=<farm_id>`

Lista las invitaciones asociadas a esa finca. `farm_id` es obligatorio para
usuarios con permisos de finca. Cada elemento contiene `id`, `farm_id`,
`email`, `status`, `invited_by`, `invited_by_name`, `user` y `created_at`.
`status` puede ser `pending`, `accepted`, `rejected` o `expired`.

### Permisos de una membresía

`PATCH /api/farms/<farm_id>/members/<user_id>/` también admite `permissions`,
una lista de permisos de finca:

```json
{
  "permissions": ["MANAGE_USERS"]
}
```

Opciones válidas: `MANAGE_REVIEWS`, `MANAGE_INVENTORY`, `MANAGE_CYCLE`,
`MANAGE_POND`, `MANAGE_FARM` y `MANAGE_USERS`. `MANAGE_USERS` permite gestionar
miembros y roles de esa finca; `MANAGE_FARM` incluye los demás permisos. Estos
permisos también pueden incluirse en el campo `permissions` al crear o editar
un rol de finca. La membresía propietaria (`is_owner: true`) no se puede editar
ni eliminar desde este endpoint; `is_owner` tampoco es modificable. Un usuario
con `MANAGE_USERS` puede administrar a los otros miembros, pero no al
propietario.

## Evaluación de permisos por app

En una solicitud dentro de una granja, los permisos del rol asignado al
operario se aplican así:

- `GET`, `HEAD` y `OPTIONS` requieren `can_view`.
- `POST` requiere `can_create`.
- `PUT` y `PATCH` requieren `can_edit`.
- `DELETE` requiere `can_delete`.
- `can_view` también debe estar activo para crear, editar o eliminar.
- El administrador conserva sus privilegios globales; el productor propietario
  conserva la administración de su propia granja.
- El nombre global de rol `Productor` no concede acceso automático a fincas:
  se requiere una membresía activa en cada finca. El propietario se identifica
  por `is_owner`.

Los permisos propios del recurso —por ejemplo, que un operario tenga asignado
un estanque— se siguen comprobando además del rol de la granja.

