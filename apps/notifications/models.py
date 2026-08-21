from django.conf import settings
from django.db import models


class NotificationLog(models.Model):
    class Channel(models.TextChoices):
        TELEGRAM = 'telegram', 'Telegram'
        MAX = 'max', 'MAX'

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
