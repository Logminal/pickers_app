from django.conf import settings
from django.db import models


class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        TELEGRAM = 'telegram', 'Telegram'
        MAX = 'max', 'MAX'
        PUSH = 'push', 'Push (браузер)'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает отправки'
        SENT = 'sent', 'Отправлено'
        FAILED = 'failed', 'Ошибка'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notifications', verbose_name='Пользователь',
        help_text='Пусто — уведомление адресовано общему чату менеджеров/админов, не конкретному человеку',
    )
    channel = models.CharField('Канал', max_length=20, choices=Channel.choices, default=Channel.TELEGRAM)
    event_type = models.CharField('Тип события', max_length=100)
    message = models.TextField('Сообщение')
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    sent_at = models.DateTimeField('Отправлено', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'

    def __str__(self):
        return f'{self.event_type} -> {self.user or "общий чат менеджеров"} [{self.status}]'


class PushSubscription(models.Model):
    """Подписка браузера на Web Push (RFC 8291/8292) — один пользователь может
    иметь несколько подписок (телефон + компьютер и т.д.), шлём во все сразу."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='push_subscriptions', verbose_name='Пользователь',
    )
    endpoint = models.URLField('Endpoint', max_length=500, unique=True)
    p256dh = models.CharField('Ключ p256dh', max_length=255)
    auth = models.CharField('Ключ auth', max_length=255)
    user_agent = models.CharField('User-Agent', max_length=255, blank=True)
    created_at = models.DateTimeField('Подключено', auto_now_add=True)

    class Meta:
        verbose_name = 'Push-подписка браузера'
        verbose_name_plural = 'Push-подписки браузера'

    def __str__(self):
        return f'{self.user} — {self.endpoint[:60]}'
