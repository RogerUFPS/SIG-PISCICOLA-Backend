import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

AUTH_USER_MODEL = "accounts.User"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # Apps
    "apps.core",
    "apps.accounts",
    "apps.farms",
    "apps.ponds",
    "apps.batch",
    "apps.cycle",
    "apps.events",
    "apps.species",
    "apps.products",
    "apps.purchases",
    "apps.feeding",
    "apps.monitoring",
    "apps.harvest",
    "apps.health",
    "apps.sales",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.ForceTempPasswordChangeMiddleware",
]

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.authentication.SessionJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "apps.accounts.permissions.AppPermission",
    ),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Tu API",
    "DESCRIPTION": "Descripción de tu proyecto",
    "VERSION": "1.0.0",
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.LockableModelBackend",
]

JWT_IDLE_TIMEOUT = timedelta(
    minutes=int(os.getenv("JWT_IDLE_TIMEOUT_MINUTES", "15"))
)
JWT_SESSION_ABSOLUTE_LIFETIME = timedelta(
    days=int(os.getenv("JWT_SESSION_ABSOLUTE_LIFETIME_DAYS", "7"))
)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": JWT_SESSION_ABSOLUTE_LIFETIME,
    "REFRESH_TOKEN_LIFETIME": JWT_SESSION_ABSOLUTE_LIFETIME,
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

ROOT_URLCONF = "project.urls"
WSGI_APPLICATION = "project.wsgi.application"
STATIC_URL = "/static/"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
