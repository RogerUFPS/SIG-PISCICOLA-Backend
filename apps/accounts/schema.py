from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SessionJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.SessionJWTAuthentication"
    name = "sessionJwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT asociado a una sesión activa. "
                "Envíelo como Authorization: Bearer <token>."
            ),
        }
