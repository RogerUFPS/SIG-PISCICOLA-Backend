# Authentication and farm permissions

## Account sessions

Each account has one active session. It expires after 15 minutes without
activity. Authenticated requests and token refreshes extend that timeout.
Logging in with valid credentials revokes the previous session and creates a
new one; invalid credentials do not affect the current session.

## Farm permissions

Farm roles and personalized permissions are documented in the
[frontend integration guide](./frontend-permissions-guide.md). That guide
describes the API contract, role-to-module grants, additive single-operation
personal grants, effective permissions, and the user invitation flow.
