from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        abstract = True


class PersonalDataAccessLog(TimeStampedModel):
    """Журнал доступа к персональным данным (152-ФЗ, п.2.3 ТЗ)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Пользователь',
    )
    target_collector = models.ForeignKey(
        'collectors.CollectorProfile', on_delete=models.CASCADE, related_name='access_logs',
        verbose_name='Сборщик',
    )
    action = models.CharField('Действие', max_length=100)  # например: "viewed_passport_scan"
    ip_address = models.GenericIPAddressField('IP-адрес', null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Журнал доступа к персональным данным'
        verbose_name_plural = 'Журнал доступа к персональным данным'

    def __str__(self):
        return f'{self.user} -> {self.action} ({self.target_collector}) at {self.created_at}'
