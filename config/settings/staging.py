"""
Временные настройки для тестового деплоя на сервер, отличаются от prod.py
пока только менее строгими security-заголовками. База данных — PostgreSQL
(та же схема, что и в prod.py), настраивается через переменные окружения.
"""

import os

from .base import *  # noqa

DEBUG = False

ALLOWED_HOSTS = [h for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h]
CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'montash'),
        'USER': os.getenv('DB_USER', 'montash'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# За nginx с настоящим HTTPS (Let's Encrypt) — безопасно включить.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
