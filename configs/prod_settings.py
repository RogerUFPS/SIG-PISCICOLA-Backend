import os

from .base import *

DEBUG = False
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",") if os.getenv("ALLOWED_HOSTS") else []
CORS_ALLOW_ALL_ORIGINS = False
HOST_URL = os.getenv("HOST_URL") or "https://sig-piscicola-frontend.vercel.app"
