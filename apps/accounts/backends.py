# backends.py
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

from .models import User

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 1


class LockableModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get("email")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return None

        if user.is_locked:
            return None

        if not user.check_password(password):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_ATTEMPTS:
                user.account_locked_until = timezone.now() + timezone.timedelta(
                    minutes=LOCKOUT_MINUTES
                )
            user.save(update_fields=["failed_login_attempts", "account_locked_until"])
            return None

        if user.failed_login_attempts > 0:
            user.failed_login_attempts = 0
            user.account_locked_until = None
            user.save(update_fields=["failed_login_attempts", "account_locked_until"])

        return user if self.user_can_authenticate(user) else None
