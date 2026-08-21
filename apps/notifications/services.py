import logging

import requests
from django.conf import settings
from django.utils import timezone

from .models import NotificationLog

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = 'https://api.telegram.org/bot{token}/sendMessage'


def notify(user, event_type, message, channel=NotificationLog.Channel.TELEGRAM):
    """Синхронная отправка уведомления (без очереди — экономия памяти на слабом VDS,
    см. обсуждение архитектуры). Если начнёт тормозить запросы — тогда переходить на очередь.
    """
    log = NotificationLog.objects.create(
        user=user, channel=channel, event_type=event_type, message=message,
    )

    if channel == NotificationLog.Channel.TELEGRAM:
        _send_telegram(log)

    return log


def _send_telegram(log: NotificationLog):
    telegram_chat_id = getattr(log.user, 'telegram_chat_id', None)
    if not telegram_chat_id or not settings.TELEGRAM_BOT_TOKEN:
        log.status = NotificationLog.Status.FAILED
        log.save(update_fields=['status'])
        return

    url = TELEGRAM_API_URL.format(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        response = requests.post(url, json={'chat_id': telegram_chat_id, 'text': log.message}, timeout=10)
        response.raise_for_status()
        log.status = NotificationLog.Status.SENT
        log.sent_at = timezone.now()
    except requests.RequestException:
        logger.exception('Не удалось отправить Telegram-уведомление user_id=%s', log.user_id)
        log.status = NotificationLog.Status.FAILED
    log.save(update_fields=['status', 'sent_at'])
