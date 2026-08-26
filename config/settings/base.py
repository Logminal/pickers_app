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

# За nginx TLS завершается на прокси — без этого Django не видит запрос как
# HTTPS и SECURE_SSL_REDIRECT в prod/staging уходит в бесконечный редирект.
# Требует, чтобы nginx всегда ставил X-Forwarded-Proto (см. конфиги на сервере).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Реальная отправка в Telegram/MAX/push уходит в фоновый поток, а не блокирует
# ответ пользователю (см. apps/notifications/services.py) — сеть до этих API
# не всегда доступна с сервера, и синхронное ожидание таймаута вешает сайт
# при малом числе воркеров. В тестах отключается через override_settings.
NOTIFY_ASYNC = True

# Telegram Bot API (уведомления, п.6 ТЗ)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', '')

# Общий чат менеджеров/админов — если задан, все уведомления, адресованные
# этой роли, идут одним сообщением сюда вместо личных Telegram каждого менеджера.
# Узнать id чата: добавить бота в группу и отправить там команду /id.
TELEGRAM_STAFF_GROUP_CHAT_ID = os.getenv('TELEGRAM_STAFF_GROUP_CHAT_ID', '')

# MAX Bot API (п.6 ТЗ) — второй канал уведомлений, пользователь сам выбирает
# канал(ы) в личном кабинете (см. apps/notifications). API похож на Telegram:
# токен в заголовке Authorization, отправка POST /messages?chat_id=..,
# получение обновлений GET /updates (long polling, курсор — marker).
MAX_BOT_TOKEN = os.getenv('MAX_BOT_TOKEN', '')
MAX_BOT_USERNAME = os.getenv('MAX_BOT_USERNAME', '')

# Сертификат platform-api2.max.ru выпущен российским государственным УЦ
# (Минцифры, "Russian Trusted CA") — его нет в стандартных доверенных
# хранилищах вне РФ, поэтому обычная проверка SSL для этого домена падает
# с "unable to get local issuer certificate". Официальная цепочка сохранена
# в репозитории (certs/russian_trusted_ca_bundle.pem, источник — gu-st.ru)
# и передаётся явно в requests(verify=...) — важно: НЕ отключать проверку
# (verify=False) вместо этого, так теряется защита от подмены сертификата.
MAX_CA_BUNDLE = str(BASE_DIR / 'certs' / 'russian_trusted_ca_bundle.pem')

# Bitrix24 (п.8 ТЗ) — входящий вебхук, цена берётся из поля OPPORTUNITY сделки
# (уточнено с заказчиком: цена хранится именно в сделке, не в товаре каталога).
BITRIX_WEBHOOK_URL = os.getenv('BITRIX_WEBHOOK_URL', '')

# Web Push (RFC 8291/8292) — третий канал уведомлений, приходит от самого
# приложения (не через Telegram/MAX), работает даже когда PWA закрыто.
# Сгенерировать пару ключей: manage.py generate_vapid_keys
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '')
VAPID_CLAIM_EMAIL = os.getenv('VAPID_CLAIM_EMAIL', '')

# Открытый вопрос №3 из ТЗ: лимит одновременно забронированных заявок у одного
# сборщика, чтобы не набирал больше, чем может выполнить. Значение по умолчанию —
# временное, обсудить с заказчиком и вынести в справочник/настройки компании при необходимости.
MAX_ACTIVE_BOOKINGS_PER_COLLECTOR = int(os.getenv('MAX_ACTIVE_BOOKINGS_PER_COLLECTOR', '2'))

# Ключ шифрования сканов паспорта (152-ФЗ, п.2.3 ТЗ) — см. apps/collectors/storage.py.
# В .env ОБЯЗАТЕЛЬНО задать свой PASSPORT_ENCRYPTION_KEY в проде (Fernet.generate_key()).
# Фолбэк ниже выводится из SECRET_KEY только чтобы dev-окружение работало "из коробки" —
# для прода полагаться на него нельзя.
PASSPORT_ENCRYPTION_KEY = os.getenv('PASSPORT_ENCRYPTION_KEY') or base64.urlsafe_b64encode(
    hashlib.sha256(SECRET_KEY.encode()).digest()
)
if isinstance(PASSPORT_ENCRYPTION_KEY, str):
    PASSPORT_ENCRYPTION_KEY = PASSPORT_ENCRYPTION_KEY.encode()
