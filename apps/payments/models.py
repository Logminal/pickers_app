from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class PaymentRecord(TimeStampedModel):
    """Факт 'заявка закрыта -> сумма к выплате'. Сама выплата происходит вне системы (п.5 ТЗ)."""

    order = models.OneToOneField(
        'orders.Order', on_delete=models.CASCADE, related_name='payment_record', verbose_name='Заявка',
    )
    collector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payment_records',
        verbose_name='Сборщик',
    )
    amount = models.DecimalField('Сумма', max_digits=10, decimal_places=2)
    is_paid = models.BooleanField('Выплачено', default=False, help_text='Отмечается вручную менеджером/админом при выплате')
    paid_at = models.DateTimeField('Дата выплаты', null=True, blank=True)

    class Meta:
        verbose_name = 'Запись о выплате'
        verbose_name_plural = 'Записи о выплатах'

    def __str__(self):
        return f'{self.collector} — {self.amount} ₽ (заявка #{self.order_id})'


class Rating(TimeStampedModel):
    """Оценка сборщика менеджером после каждой заявки (п.5 ТЗ)."""

    order = models.OneToOneField('orders.Order', on_delete=models.CASCADE, related_name='rating', verbose_name='Заявка')
    collector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ratings', verbose_name='Сборщик',
    )
    rated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='given_ratings',
        verbose_name='Кто оценил',
    )
    score = models.PositiveSmallIntegerField('Оценка', help_text='1-5')
    deadline_met = models.BooleanField('Срок соблюдён', default=True)
    had_complaint = models.BooleanField('Была рекламация', default=False)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Оценка'
        verbose_name_plural = 'Оценки'

    def __str__(self):
        return f'{self.collector} — {self.score}/5 (заявка #{self.order_id})'
