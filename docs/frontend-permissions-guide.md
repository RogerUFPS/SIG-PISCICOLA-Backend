# Frontend integration guide: roles and permissions

All paths below are relative to `/api`. Authenticated requests use the access
token in `Authorization: Bearer <access-token>`. IDs in examples are
illustrative.

## Permission model

The global account role (`Admin`, `Productor`, or `Operario`) is distinct from
a farm role. A farm role belongs to one farm and defines exactly which of
`view`, `create`, `update`, and `delete` are allowed for each business module.
For example, `can_update: true` does not imply `can_view: true`.

The effective farm permissions are:

```text
role grants ∪ personalized grants
```

Personalized permissions are additive-only, each one being exactly one
`module` plus one `operation`. They cannot deny or change role permissions.
Removing a personalized permission only removes that individual grant; if the
role grants the same operation, it remains effective. An absent personalized
permission means “no change.”

The farm owner and global `Admin` retain their existing administrative bypass.
For members, permissions are evaluated on every request, so role changes apply
immediately, including to users with an active session.

### Module identifiers

Use the identifiers returned by `GET farms/{farm_id}/roles/modules/`. These are
business capability names, not application-directory names.

| `module` | Display name |
| --- | --- |
| `production_batches` | Production batches |
| `production_cycles` | Production cycles |
| `farm_events` | Farm events |
| `feeding_management` | Feeding management |
| `harvest_management` | Harvest management |
| `fish_health` | Fish health |
| `water_quality_monitoring` | Water quality monitoring |
| `pond_management` | Pond management |
| `inventory_products` | Product inventory |
| `inventory_purchases` | Purchasing |
| `inventory_sales` | Sales |
| `species_catalog` | Species catalog |
| `farm_management` | Farm management |
| `alerts` | Alerts (view only) |
| `audit_logs` | Audit logs (view only) |
| `user_administration` | User administration |

Operations are independent. `GET`, `HEAD`, and `OPTIONS` use `view`; `POST`
uses `create`; `PUT` and `PATCH` use `update`; `DELETE` uses `delete`.

## Roles

### `GET farms/{farm_id}/roles/modules/`

Requires `user_administration.view`, or farm-owner/`Admin` access. Returns
`200 OK` and the module catalog:

```json
[
  {"module": "fish_health", "name": "Fish health"},
  {"module": "user_administration", "name": "User administration"}
]
```

### `GET farms/{farm_id}/roles/`

Requires `user_administration.view`, or farm-owner/`Admin` access. Returns
`200 OK` and the farm's active roles. Each role has this shape:

```json
{
  "id": 12,
  "farm": 8,
  "name": "Health reviewer",
  "module_permissions": [
    {
      "module": "fish_health",
      "can_view": true,
      "can_create": false,
      "can_update": true,
      "can_delete": false
    }
  ]
}
```

### `POST farms/{farm_id}/roles/`

The farm owner or `Admin` creates a role. `module_permissions` can be omitted
to create a role with no module grants.

```json
{
  "name": "Health reviewer",
  "module_permissions": [
    {
      "module": "fish_health",
      "can_view": true,
      "can_create": false,
      "can_update": true,
      "can_delete": false
    }
  ]
}
```

Returns `201 Created` with the role representation. Module identifiers must
exist in the catalog, and a module may appear only once. `alerts` and
`audit_logs` accept only `can_view`.

### `GET farms/{farm_id}/roles/{role_id}/`

Requires `user_administration.view`, or farm-owner/`Admin` access. Returns
`200 OK` with one role in the same shape as the list item.

### `PUT farms/{farm_id}/roles/{role_id}/` and
`PATCH farms/{farm_id}/roles/{role_id}/`

The farm owner or `Admin` updates a role. When included,
`module_permissions` replaces that role's complete module-grant list. Send an
empty list to clear its role grants:

```json
{"module_permissions": []}
```

Omitting `module_permissions` leaves the grants unchanged. Returns `200 OK`.
The change affects all assigned members immediately and does not delete or
modify their personalized permissions.

### `DELETE farms/{farm_id}/roles/{role_id}/`

The farm owner or `Admin` deactivates the role. Returns `204 No Content`.
Members are unassigned from the role; their personalized grants remain.

## Members and effective permissions

### `GET farms/{farm_id}/members/` and
`GET farms/{farm_id}/members/{user_id}/`

Return `200 OK`. A member representation is:

```json
{
  "user": {
    "id": 27,
    "name": "Ana",
    "lastname": "Pérez",
    "cc": "123456",
    "email": "ana@example.com",
    "phone": "3000000000"
  },
  "user_id": 27,
  "farm": 8,
  "farm_role": 12,
  "personal_permissions": [
    {"id": 45, "module": "inventory_products", "operation": "create"}
  ],
  "effective_permissions": [
    {"module": "fish_health", "operation": "view"},
    {"module": "fish_health", "operation": "update"},
    {"module": "inventory_products", "operation": "create"}
  ],
  "status": "active",
  "is_owner": false
}
```

`effective_permissions` is the authoritative union the frontend should use to
show enabled operations. Do not derive it by treating missing personal grants
as denials. For a farm owner the API reports the owner's full farm access.

### `PATCH farms/{farm_id}/members/{user_id}/`

The owner or `Admin` can assign, change, or remove a farm role; use `null` to
unassign it. Personalized permissions survive role changes:

```json
{"farm_role": 12}
```

```json
{"farm_role": null}
```

The owner or `Admin` may also change membership status:

```json
{"status": "inactive"}
```

Valid status values are `active` and `inactive`. Returns `200 OK` with the
updated member, including `personal_permissions` and `effective_permissions`.
The legacy `permissions` field is not accepted; use the individual-permission
endpoints below. A role must be active and belong to this farm.

### `DELETE farms/{farm_id}/members/{user_id}/`

Removes the membership and its farm-scoped personalized grants. It does not
delete the global user account. Returns `204 No Content`. The farm owner cannot
be removed.

## Personalized permissions

Only the farm owner or `Admin` can add/remove personalized grants. The UI
should offer a single module selector and a single operation selector for each
grant. Do not offer permission bundles, deny/revoke toggles for role
operations, or a global “replace permissions” action. Show role grants,
personalized grants, and effective permissions as separate sources if useful.
Removing a personalized grant never removes a role grant.

### `POST farms/{farm_id}/members/{user_id}/personal-permissions/`

Creates one personalized grant:

```json
{"module": "inventory_products", "operation": "create"}
```

The only accepted request keys are `module` and `operation`; `operation` must
be exactly one of `view`, `create`, `update`, or `delete`. Returns `201 Created`
with `{"id": 45, "module": "inventory_products", "operation": "create"}`.
Submitting a grant already assigned to that member is harmless and returns
`200 OK` with the existing grant. `alerts` and `audit_logs` allow only `view`.
The member response should be refreshed to display the updated effective
permissions.

### `DELETE farms/{farm_id}/members/{user_id}/personal-permissions/{permission_id}/`

Removes only the specified personalized grant. Returns `204 No Content`; if the
grant does not belong to that member or does not exist, returns `404 Not Found`.
Role grants are untouched.

## User creation and invitation flow

There is no general `POST users/` endpoint for farm operators. Use the farm
invitation flow:

### `POST invitations/operario/`

Requires `user_administration.create`, or farm-owner/`Admin` access, and a farm
ID:

```json
{"email": "ana@example.com", "farm_id": 8}
```

Returns `201 Created` and `{"detail": "Invitación procesada correctamente."}`.
If the email is new, the API creates an `Operario` account and an active farm
membership; credentials are sent by email. If the account already exists, the
API creates a pending invitation; the user must accept it before a membership
is created. A duplicate membership or invalid farm returns `400 Bad Request`.

After a new account's first login, the user may need to change the temporary
password with `POST auth/change-password/` (`current_password` and
`new_password`) and complete their profile with
`POST users/me/complete/` (`name`, `lastname`, `cc`, and `phone`).

The authenticated user can read or update only their own profile with
`GET users/me/` or `PATCH users/me/`. These self-service requests do not require
a farm role or a `user_administration` grant; the endpoint always resolves the
target user from the authenticated token and does not accept a target user ID.

### `GET invitations/?farm_id={farm_id}`

Requires `user_administration.view`, or farm-owner/`Admin` access. Lists
invitations for the farm. Returns `200 OK` with an array of items shaped like:

```json
{
  "id": 31,
  "farm_id": 8,
  "email": "ana@example.com",
  "status": "pending",
  "invited_by": 4,
  "invited_by_name": "Carlos Díaz",
  "user": 27,
  "created_at": "2026-11-07T17:00:00Z"
}
```

Statuses are `pending`, `accepted`, `rejected`, and `expired`.

### `GET invitations/{invitation_id}/`

The invited user reads their invitation; returns `200 OK` with the same shape.
The request must be authenticated.

### `POST invitations/{invitation_id}/accept/` and
`POST invitations/{invitation_id}/reject/`

The invited user accepts or rejects a pending invitation. Each returns `200 OK`
with a `detail` message. An invitation that is not pending or does not belong
to the user returns `404 Not Found`. Accepting creates an active farm
membership with no assigned farm role and no personalized permissions; the
owner can then assign a role and add individual grants.

### Membership manager authority

Member reads require `user_administration.view`; changing membership status
requires `user_administration.update`; deleting a non-owner membership requires
`user_administration.delete`. Farm owners and `Admin` bypass these module
checks. A member granted these operations can manage invitations, member
status, and removals, but only the farm owner or `Admin` can create/change
roles, assign a member's role, or add/remove personalized permissions.

### First login and profile setup

#### `POST auth/login/`

Request:

```json
{"email": "ana@example.com", "password": "<password>"}
```

Returns `200 OK`:

```json
{
  "tokens": {"access": "<access-token>", "refresh": "<refresh-token>"},
  "is_profile_complete": false
}
```

Invalid credentials return `400 Bad Request` with a `detail` error.

#### `POST auth/change-password/`

Request: `{"current_password": "...", "new_password": "..."}`. A successful
change returns `200 OK` and
`{"detail": "Contraseña actualizada correctamente."}`.

#### `POST users/me/complete/`

Request: `{"name": "...", "lastname": "...", "cc": "...", "phone": "..."}`.
Success returns `200 OK` and `{"detail": "Perfil completado correctamente."}`.
Validation errors return `400 Bad Request`.

## Status codes and error payloads

- `200 OK`: successful reads and updates; duplicate personalized grant.
- `201 Created`: role, invitation, or personalized grant created.
- `204 No Content`: role deactivated, member removed, or personal grant removed.
- `400 Bad Request`: invalid module/operation, multi-operation payload, duplicate
  role module, invalid role assignment, or other validation failure.
- `401 Unauthorized`: missing, invalid, or expired authentication.
- `403 Forbidden`: authenticated user lacks the needed farm/module operation
  or management authority.
- `404 Not Found`: resource is absent, inactive, outside the farm, or not
  available to the caller.

Serializer validation errors use the standard field-to-message-array shape,
for example:

```json
{
  "operation": ["Select a valid choice. That choice is not one of the available choices."]
}
```

Permission and endpoint errors commonly use:

```json
{"detail": "No tienes permisos para administrar usuarios en esta finca."}
```

An unrecognized or extra permission key is rejected as a `400`, not silently
interpreted as a bundle.
