## Roles y permisos de operarios por granja

Los tipos globales de cuenta siguen siendo `Admin`, `Productor` y `Operario`.
Los roles que se configuran en esta sección son perfiles de trabajo locales a
una granja; no crean nuevos tipos globales de usuario. El productor propietario
administra los roles y asigna cada rol a los operarios de esa granja.

### `GET /api/farms/<farm_id>/roles/apps/`

Lista las aplicaciones instaladas bajo `apps.*` en el backend, excepto
`accounts`. La lista se obtiene del registro de aplicaciones de Django: no se
mantiene manualmente en el frontend ni en una tabla de configuración.

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
apps deben pertenecer al listado dinámico, no se pueden repetir y `can_view`
debe ser `true` si cualquiera de las otras acciones está habilitada. Si no se
envía `app_permissions`, el rol nuevo queda configurado sin permisos por app.

### `GET /api/farms/<farm_id>/roles/<role_id>/`

Obtiene un rol y sus permisos para una granja.

### `PUT /api/farms/<farm_id>/roles/<role_id>/` y
`PATCH /api/farms/<farm_id>/roles/<role_id>/`

Actualiza el rol. Si se incluye `app_permissions`, la lista reemplaza los
permisos previos del rol; si se omite, estos no cambian. Envía una lista vacía
para revocar todos los permisos por app.

Las autorizaciones consultan el rol y sus permisos en cada solicitud. Por
ello, los cambios afectan también a operarios con una sesión ya iniciada.

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

Los permisos propios del recurso —por ejemplo, que un operario tenga asignado
un estanque— se siguen comprobando además del rol de la granja.
