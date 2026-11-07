from .base import *

SECRET_KEY = "test-only-secret-key-with-enough-bytes-123456"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "testserver"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
