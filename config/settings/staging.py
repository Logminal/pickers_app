"""
Временные настройки для тестового деплоя на сервер — SQLite вместо
PostgreSQL, чтобы посмотреть на живую работу приложения без разворачивания
полноценной прод-инфраструктуры. Когда сервер будет настроен по-нормальному
(Postgres, отдельные воркеры для ботов и т.д.) — этот файл можно убрать
и перейти на prod.py.
"""

import os

from .base import *  # noqa

DEBUG = False

ALLOWED_HOSTS = [h for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h]
CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',  # noqa: F405
    }
}

# За nginx с настоящим HTTPS (Let's Encrypt) — безопасно включить.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
