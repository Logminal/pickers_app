import logging

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import NotificationLog

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = 'https://api.telegram.org/bot{token}/sendMessage'
MAX_API_URL = 'https://platform-api2.max.ru/messages'


def notify(user, event_type, message, channels=None):
    """Синхронная отправка уведомления (без очереди — экономия памяти на слабом VDS,
    см. обсуждение архитектуры). Если начнёт тормозить запросы — тогда переходить на очередь.

    Пользователь сам выбирает канал(ы) доставки в личном кабинете (notify_via_telegram/
    notify_via_max) — по умолчанию используются они; можно передать channels явно
    (например, notify_staff() всегда шлёт в Telegram, независимо от чьих-то настроек).
    Создаёт по одной записи NotificationLog на каждый фактически использованный канал.

    Если у user роль менеджер/админ и настроен TELEGRAM_STAFF_GROUP_CHAT_ID,
    Telegram-доставка всё равно уходит в общий чат менеджеров (см. _resolve_chat_id) —
    но лог по-прежнему привязан к конкретному user, это не касается notify_staff().
    """
    if channels is None:
        channels = _resolve_user_channels(user)

    logs = []
    for channel in channels:
        log = NotificationLog.objects.create(
            user=user, channel=channel, event_type=event_type, message=message,
        )
        if channel == NotificationLog.Channel.TELEGRAM:
            _send_telegram(log)
        elif channel == NotificationLog.Channel.MAX:
            _send_max(log)
        logs.append(log)

    return logs


def notify_staff(event_type, message):
    """Событие адресовано менеджерам/админам как группе, а не конкретному человеку
    (например, заявка на выплату — реагировать может любой менеджер).

    Если настроен общий чат менеджеров (TELEGRAM_STAFF_GROUP_CHAT_ID) — одно
    сообщение туда, без привязки к пользователю в логе. Иначе — каждому
    менеджеру/админу отдельно, в те каналы, которые он сам выбрал в настройках."""
    if settings.TELEGRAM_STAFF_GROUP_CHAT_ID:
        log = NotificationLog.objects.create(
            user=None, channel=NotificationLog.Channel.TELEGRAM, event_type=event_type, message=message,
        )
        _send_telegram(log)
        return [log]

    User = get_user_model()
    staff = User.objects.filter(role__in=[User.Role.MANAGER, User.Role.ADMIN])
    logs = []
    for u in staff:
        logs.extend(notify(u, event_type, message))
    return logs


def _resolve_user_channels(user):
    """Каналы, выбранные пользователем в настройках. Если он случайно снял все
    галочки — подстраховка: всё равно шлём в Telegram, чтобы не терять уведомления молча."""
    channels = []
    if getattr(user, 'notify_via_telegram', True):
        channels.append(NotificationLog.Channel.TELEGRAM)
    if getattr(user, 'notify_via_max', False):
        channels.append(NotificationLog.Channel.MAX)
    return channels or [NotificationLog.Channel.TELEGRAM]


def _resolve_chat_id(log: NotificationLog):
    User = get_user_model()

    if log.user is None:
        return settings.TELEGRAM_STAFF_GROUP_CHAT_ID or None

    if log.user.role in (User.Role.MANAGER, User.Role.ADMIN) and settings.TELEGRAM_STAFF_GROUP_CHAT_ID:
        return settings.TELEGRAM_STAFF_GROUP_CHAT_ID

    return getattr(log.user, 'telegram_chat_id', None)


def _send_telegram(log: NotificationLog):
    chat_id = _resolve_chat_id(log)
    if not chat_id or not settings.TELEGRAM_BOT_TOKEN:
        log.status = NotificationLog.Status.FAILED
        log.save(update_fields=['status'])
        return

    url = TELEGRAM_API_URL.format(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        response = requests.post(url, json={'chat_id': chat_id, 'text': log.message}, timeout=10)
        response.raise_for_status()
        log.status = NotificationLog.Status.SENT
        log.sent_at = timezone.now()
    except requests.RequestException:
        logger.exception('Не удалось отправить Telegram-уведомление user_id=%s', log.user_id)
        log.status = NotificationLog.Status.FAILED
    log.save(update_fields=['status', 'sent_at'])


def _send_max(log: NotificationLog):
    chat_id = getattr(log.user, 'max_chat_id', None) if log.user else None
    if not chat_id or not settings.MAX_BOT_TOKEN:
        log.status = NotificationLog.Status.FAILED
        log.save(update_fields=['status'])
        return

    try:
        response = requests.post(
            MAX_API_URL,
            params={'chat_id': chat_id},
            json={'text': log.message, 'attachments': []},
            headers={'Authorization': settings.MAX_BOT_TOKEN},
            timeout=10,
            verify=settings.MAX_CA_BUNDLE,
        )
        response.raise_for_status()
        log.status = NotificationLog.Status.SENT
        log.sent_at = timezone.now()
    except requests.RequestException:
        logger.exception('Не удалось отправить MAX-уведомление user_id=%s', log.user_id)
        log.status = NotificationLog.Status.FAILED
    log.save(update_fields=['status', 'sent_at'])
