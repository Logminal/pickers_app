from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

from apps.core.models import TimeStampedModel

RECEIPT_EXTENSIONS = ['jpg', 'jpeg', 'png', 'pdf']


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


class WithdrawalRequest(TimeStampedModel):
    """Сборщик запрашивает вывод накопленного баланса. Сама выплата происходит вне
    системы — менеджер созванивается со сборщиком и переводит/передаёт деньги, после
    чего отмечает заявку выполненной."""

    class Method(models.TextChoices):
        IN_PERSON = 'in_person', 'Лично в руки'
        PHONE_TRANSFER = 'phone_transfer', 'Перевод по номеру телефона'
        CARD_TRANSFER = 'card_transfer', 'Перевод на карту'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает звонка'
        COMPLETED = 'completed', 'Выплачено'
        CANCELLED = 'cancelled', 'Отменена'

    collector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='withdrawal_requests',
        verbose_name='Сборщик',
    )
    payment_records = models.ManyToManyField(
        PaymentRecord, related_name='withdrawal_requests', verbose_name='Включённые начисления',
    )
    amount = models.DecimalField('Сумма к выплате', max_digits=10, decimal_places=2)
    method = models.CharField('Способ получения', max_length=20, choices=Method.choices)
    requisite = models.CharField(
        'Номер карты/телефона', max_length=50, blank=True,
        help_text='Заполняется для перевода по карте или по номеру телефона',
    )
    comment = models.CharField('Комментарий сборщика', max_length=255, blank=True)
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.PENDING)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='handled_withdrawal_requests', verbose_name='Кто обработал',
    )
    completed_at = models.DateTimeField('Дата выплаты', null=True, blank=True)
    # Обязателен при завершении выплаты переводом (card_transfer/phone_transfer) —
    # см. services.complete_withdrawal_request. Для in_person не нужен.
    receipt = models.FileField(
        'Чек/квитанция о переводе', upload_to='payments/receipts/%Y/%m/', null=True, blank=True,
        validators=[FileExtensionValidator(allowed_extensions=RECEIPT_EXTENSIONS)],
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заявка на выплату'
        verbose_name_plural = 'Заявки на выплату'

    def __str__(self):
        return f'{self.collector} — {self.amount} ₽ ({self.get_status_display()})'
