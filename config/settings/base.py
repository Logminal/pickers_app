"""
Базовые настройки проекта. Общие для dev и prod.
Специфичные для окружения настройки — в dev.py / prod.py.
"""

import base64
import hashlib
from pathlib import Path
import os

from dotenv import load_dotenv

# BASE_DIR — корень репозитория (config/settings/base.py -> ../../..)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-change-me-in-env')

DEBUG = False

ALLOWED_HOSTS = []


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # local apps
    'apps.core',
    'apps.users',
    'apps.collectors',
    'apps.orders',
    'apps.reports',
    'apps.payments',
    'apps.dictionaries',
    'apps.notifications',
    'apps.integrations',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

AUTH_USER_MODEL = 'users.User'

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'order_list'
LOGOUT_REDIRECT_URL = 'login'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Приватное хранилище для чувствительных файлов (сканы паспортов, фотоотчёты).
# В dev — локальная папка вне media/ (не отдаётся статикой напрямую).
# В prod — переключить на сетевой диск/S3-совместимое хранилище (см. apps/collectors/storage.py).
PRIVATE_STORAGE_ROOT = BASE_DIR / 'private_storage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Telegram Bot API (уведомления, п.6 ТЗ)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Открытый вопрос №3 из ТЗ: лимит одновременно забронированных заявок у одного
# сборщика, чтобы не набирал больше, чем может выполнить. Значение по умолчанию —
# временное, обсудить с заказчиком и вынести в справочник/настройки компании при необходимости.
MAX_ACTIVE_BOOKINGS_PER_COLLECTOR = int(os.getenv('MAX_ACTIVE_BOOKINGS_PER_COLLECTOR', '3'))

# Ключ шифрования сканов паспорта (152-ФЗ, п.2.3 ТЗ) — см. apps/collectors/storage.py.
# В .env ОБЯЗАТЕЛЬНО задать свой PASSPORT_ENCRYPTION_KEY в проде (Fernet.generate_key()).
# Фолбэк ниже выводится из SECRET_KEY только чтобы dev-окружение работало "из коробки" —
# для прода полагаться на него нельзя.
PASSPORT_ENCRYPTION_KEY = os.getenv('PASSPORT_ENCRYPTION_KEY') or base64.urlsafe_b64encode(
    hashlib.sha256(SECRET_KEY.encode()).digest()
)
if isinstance(PASSPORT_ENCRYPTION_KEY, str):
    PASSPORT_ENCRYPTION_KEY = PASSPORT_ENCRYPTION_KEY.encode()
