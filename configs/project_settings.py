import os
from datetime import timedelta
from datetime import timedelta

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

from .base import *

load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DEBUG", "True") == "True"
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set SECRET_KEY when DEBUG is disabled.")
    SECRET_KEY = "django-insecure-dev-only"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME"),
        "USER": os.getenv("DATABASE_USER"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD"),
        "HOST": os.getenv("DATABASE_HOST", "db"),
        "PORT": os.getenv("DATABASE_PORT", "5432"),
        "OPTIONS": {"sslmode": os.getenv("DATABASE_SSLMODE", "require")},
    }
}

CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "True") == "True"
HOST_URL = os.getenv("HOST_URL") or "https://sig-piscicola-frontend.vercel.app"
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
JWT_IDLE_TIMEOUT = timedelta(
    minutes=int(os.getenv("JWT_IDLE_TIMEOUT_MINUTES", "15"))
)
JWT_SESSION_ABSOLUTE_LIFETIME = timedelta(
    days=int(os.getenv("JWT_SESSION_ABSOLUTE_LIFETIME_DAYS", "7"))
)
