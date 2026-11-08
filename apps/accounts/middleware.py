# middleware.py
from django.http import JsonResponse

TEMP_PASSWORD_EXEMPT = {
    "/api/auth/change-password/",
    "/api/auth/logout/",
    "/api/users/me/complete/",
}

PROFILE_EXEMPT = {"/api/users/me/complete/", "/api/auth/logout/"}


class ForceTempPasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path
        if (
            user
            and user.is_authenticated
            and getattr(user, "is_temp_password", False)
            and path not in TEMP_PASSWORD_EXEMPT
            and not any(path.startswith(prefix) for prefix in TEMP_PASSWORD_EXEMPT)
        ):
            return JsonResponse(
                {"detail": "Debes cambiar tu contraseña antes de continuar."},
                status=403,
            )
        if (
            user
            and user.is_authenticated
            and not getattr(user, "is_profile_complete", True)
            and path not in PROFILE_EXEMPT
            and not any(path.startswith(prefix) for prefix in PROFILE_EXEMPT)
        ):
            return JsonResponse(
                {"detail": "Debes completar tu perfil antes de continuar."},
                status=403,
            )
        return self.get_response(request)
