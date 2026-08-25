import json
import logging
import threading

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone
from pywebpush import WebPushException, webpush

from .models import NotificationLog, PushSubscription

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = 'https://api.telegram.org/bot{token}/sendMessage'
MAX_API_URL = 'https://platform-api2.max.ru/messages'

# Сеть до Telegram/MAX с этого VDS не всегда доступна (например, у Timeweb
# бывает недоступен api.telegram.org — реальный кейс, полное зависание на
# все 10 сек таймаута). Раньше отправка была синхронной ("без очереди —
# экономия памяти на слабом VDS"), и один такой зависший запрос при всего
# 2 воркерах gunicorn на одном ядре означал, что сайт переставал отвечать
# ВСЕМ пользователям на эти же 10 секунд. NOTIFY_ASYNC уводит саму отправку
# в отдельный поток, чтобы ответ пользователю не ждал сеть до чужого API —
# это по-прежнему не очередь (Celery/Redis тут явно лишние), просто поток,
# в тестах отключается через override_settings(NOTIFY_ASYNC=False) ради
# детерминированных assert'ов сразу после notify().


def notify(user, event_type, message, channels=None):
    """Пользователь сам выбирает канал(ы) доставки в личном кабинете (notify_via_telegram/
    notify_via_max/notify_via_push) — по умолчанию используются они; можно передать channels
    явно (например, notify_staff() всегда шлёт в Telegram, независимо от чьих-то настроек).
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
        _dispatch(channel, log)
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
        _dispatch(NotificationLog.Channel.TELEGRAM, log)
        return [log]

    User = get_user_model()
    staff = User.objects.filter(role__in=[User.Role.MANAGER, User.Role.ADMIN])
    logs = []
    for u in staff:
        logs.extend(notify(u, event_type, message))
    return logs


_SENDERS = {
    NotificationLog.Channel.TELEGRAM: '_send_telegram',
    NotificationLog.Channel.MAX: '_send_max',
    NotificationLog.Channel.PUSH: '_send_push',
}


def _dispatch(channel, log):
    sender_name = _SENDERS.get(channel)
    if not sender_name:
        return
    sender = globals()[sender_name]
    if getattr(settings, 'NOTIFY_ASYNC', True):
        threading.Thread(target=_send_in_background, args=(sender, log), daemon=True).start()
    else:
        sender(log)


def _send_in_background(sender, log):
    try:
        sender(log)
    finally:
        connections.close_all()


def _resolve_user_channels(user):
    """Каналы, выбранные пользователем в настройках. Если он случайно снял все
    галочки — подстраховка: всё равно шлём в Telegram, чтобы не терять уведомления молча."""
    channels = []
    if getattr(user, 'notify_via_telegram', True):
        channels.append(NotificationLog.Channel.TELEGRAM)
    if getattr(user, 'notify_via_max', False):
        channels.append(NotificationLog.Channel.MAX)
    if getattr(user, 'notify_via_push', False):
        channels.append(NotificationLog.Channel.PUSH)
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


def _send_push(log: NotificationLog):
    """Шлём во все подписки пользователя разом (может быть несколько устройств/
    браузеров) — успех, если хотя бы одна доставка прошла. Битые подписки
    (404/410 — пользователь отключил уведомления в браузере или переустановил
    PWA) удаляем сразу, чтобы не пытаться слать в них снова и снова."""
    if not log.user or not settings.VAPID_PRIVATE_KEY:
        log.status = NotificationLog.Status.FAILED
        log.save(update_fields=['status'])
        return

    subscriptions = list(log.user.push_subscriptions.all())
    if not subscriptions:
        log.status = NotificationLog.Status.FAILED
        log.save(update_fields=['status'])
        return

    payload = json.dumps({'title': 'Сборка мебели', 'body': log.message})
    sent = False
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': settings.VAPID_CLAIM_EMAIL},
                timeout=10,
            )
            sent = True
        except WebPushException as exc:
            status_code = getattr(exc.response, 'status_code', None)
            if status_code in (404, 410):
                sub.delete()
            else:
                logger.exception('Не удалось отправить push-уведомление user_id=%s', log.user_id)

    log.status = NotificationLog.Status.SENT if sent else NotificationLog.Status.FAILED
    if sent:
        log.sent_at = timezone.now()
    log.save(update_fields=['status', 'sent_at'])
