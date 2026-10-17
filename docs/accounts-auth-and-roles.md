# Autenticación y permisos por aplicación

Base URL de los endpoints: `/api`.

## Sesiones y tokens

### `POST /api/auth/login/`

El formato de credenciales no cambia. La respuesta incluye los tokens JWT y el
estado del perfil:

```json
{
  "tokens": {
    "access": "<access-token>",
    "refresh": "<refresh-token>"
  },
  "is_profile_complete": true
}
```

Los tokens emitidos inician una sesión registrada en el backend. El cliente debe
enviar el access token en las solicitudes autenticadas:

```http
Authorization: Bearer <access-token>
```

Cada solicitud autenticada renueva la marca de actividad. Una sesión se revoca
si transcurren 15 minutos sin actividad autenticada. El valor se configura con
`JWT_IDLE_TIMEOUT_MINUTES` (predeterminado: `15`). También existe un vencimiento
absoluto para la sesión: `JWT_SESSION_ABSOLUTE_LIFETIME_DAYS` (predeterminado:
`7`), que no se prolonga con la actividad.

### `POST /api/auth/token/refresh/`

Usa el refresh token de una sesión vigente para renovar los tokens. El endpoint
mantiene la rotación de refresh tokens existente.

Solicitud:

```json
{
  "refresh": "<refresh-token>"
}
```

Respuesta exitosa (`200 OK`):

```json
{
  "access": "<nuevo-access-token>",
  "refresh": "<nuevo-refresh-token>"
}
```

La renovación cuenta como actividad de la sesión. Si la sesión está revocada,
superó el límite absoluto o lleva 15 minutos inactiva, la solicitud falla con
`400 Bad Request`; el cliente debe iniciar sesión de nuevo.

### `POST /api/auth/logout/`

El logout ya no requiere un access token vigente. Envía el refresh token para
revocar la sesión e invalidar el refresh token:

```json
{
  "refresh": "<refresh-token>"
}
```

Respuesta exitosa: `204 No Content`. Si falta el refresh token o es inválido,
responde `400 Bad Request` con un campo `detail`.

### Recuperación de contraseña

Los endpoints conservan sus rutas y payloads:

- `POST /api/auth/reset-password/`: solicita el correo de recuperación.
- `GET /api/auth/reset-password/<uuidb64>/<token>/`: comprueba el token.
- `POST /api/auth/reset-password/<uuidb64>/<token>/`: confirma la nueva
  contraseña.

El enlace enviado por correo ahora apunta al frontend
`https://sig-piscicola-frontend.vercel.app/`. `HOST_URL` permite sobrescribir
esa URL por entorno.

## Administración de roles

Todos los endpoints de roles requieren autenticación de un usuario con rol
`Admin`. Para escribir los permisos de una app, incluye `app_permissions` en
el objeto del rol.

### `GET /api/roles/apps/`

Lista las aplicaciones habilitadas para configurar permisos. El valor `app` de
cada elemento es la clave que se debe usar en `app_permissions`.

Respuesta (`200 OK`):

```json
[
  {
    "app": "farms",
    "name": "Farms"
  },
  {
    "app": "ponds",
    "name": "Ponds"
  }
]
```

### `GET /api/roles/`

Lista roles y sus permisos por aplicación. Cada permiso contiene:

| Campo | Tipo | Significado |
| --- | --- | --- |
| `app` | string | Clave de aplicación, obtenida de `/api/roles/apps/`. |
| `can_view` | boolean | Puede consultar/leer. |
| `can_create` | boolean | Puede crear. |
| `can_edit` | boolean | Puede actualizar. |
| `can_delete` | boolean | Puede eliminar. |

### `POST /api/roles/`

Crea un rol y, opcionalmente, sus permisos:

```json
{
  "name": "Gestor",
  "app_permissions": [
    {
      "app": "farms",
      "can_view": true,
      "can_create": true,
      "can_edit": true,
      "can_delete": false
    },
    {
      "app": "ponds",
      "can_view": true,
      "can_create": false,
      "can_edit": false,
      "can_delete": false
    }
  ]
}
```

Las claves de aplicación deben existir y no pueden repetirse en el mismo rol.
`can_view` debe ser `true` cuando se active cualquiera de los otros permisos.
Si se omite `app_permissions` al crear el rol, empieza sin permisos por app.

### `GET /api/roles/<id>/`

Obtiene un rol con sus permisos por aplicación.

### `PUT /api/roles/<id>/` y `PATCH /api/roles/<id>/`

Actualiza los datos del rol. Si se incluye `app_permissions`, la lista enviada
reemplaza todos los permisos anteriores del rol; si se omite, los permisos no
cambian. Para retirar permisos de una app, envía la lista sin esa app.

Los cambios se consultan al autorizar cada solicitud: se aplican también a
usuarios que ya tienen una sesión iniciada, sin esperar a que renueven el JWT.

### `DELETE /api/roles/<id>/`

Elimina el rol si no tiene usuarios asignados. Si hay usuarios que lo usan,
responde `409 Conflict`.

## Aplicación de los permisos

Los permisos se evalúan para cada aplicación:

- `GET`, `HEAD` y `OPTIONS` requieren `can_view`.
- `POST` requiere `can_create`.
- `PUT` y `PATCH` requieren `can_edit`.
- `DELETE` requiere `can_delete`.
- Consultar una aplicación requiere `can_view`, incluso cuando también se
  permita crear, editar o eliminar.
- El rol `Admin` conserva acceso administrativo y no depende de filas de
  permisos por app.

Los controles propios de cada recurso, como la pertenencia a una granja,
continúan aplicándose además de los permisos por app.
