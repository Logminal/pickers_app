from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = 'new', 'Новая'
        PUBLISHED = 'published', 'Опубликована'
        BOOKED = 'booked', 'Забронирована'
        CONFIRMED = 'confirmed', 'Подтверждена админом'
        IN_PROGRESS = 'in_progress', 'В работе'
        REPORT_UPLOADED = 'report_uploaded', 'Фотоотчёт загружен'
        REJECTED_FOR_REWORK = 'rejected_for_rework', 'Отклонена (доработка)'
        ACCEPTED = 'accepted', 'Принята менеджером'
        CLOSED = 'closed', 'Закрыта'
        CANCELLED = 'cancelled', 'Отменена менеджером'
        BOOKING_REVOKED = 'booking_revoked', 'Бронь снята'
        DISPUTED = 'disputed', 'Спор/рекламация'

    class Urgency(models.TextChoices):
        NORMAL = 'normal', 'Обычная'
        URGENT = 'urgent', 'Срочная'

    furniture_type = models.ForeignKey(
        'dictionaries.FurnitureType', on_delete=models.PROTECT, related_name='orders',
        verbose_name='Тип мебели',
    )
    required_specialization = models.ForeignKey(
        'dictionaries.Specialization', on_delete=models.SET_NULL, null=True, blank=True, related_name='orders',
        verbose_name='Требуемая специализация',
    )

    address = models.CharField('Адрес объекта', max_length=500)
    address_lat = models.DecimalField('Широта', max_digits=9, decimal_places=6, null=True, blank=True)
    address_lng = models.DecimalField('Долгота', max_digits=9, decimal_places=6, null=True, blank=True)

    scheduled_at = models.DateTimeField('Желаемая дата/время выполнения')
    deadline_at = models.DateTimeField('Крайний срок сдачи')
    urgency = models.CharField('Срочность', max_length=20, choices=Urgency.choices, default=Urgency.NORMAL)

    spec_file = models.FileField(
        'Спецификация (Базис)', upload_to='orders/specs/', blank=True, null=True,
    )
    dimensions = models.CharField('Габариты', max_length=255, blank=True)
    modules_count = models.PositiveSmallIntegerField('Количество модулей', null=True, blank=True)

    price = models.DecimalField(
        'Стоимость работы', max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)],
    )
    bitrix_deal_id = models.CharField('ID сделки в Bitrix24', max_length=50, blank=True)

    # Разбивка стоимости из сделки Bitrix24 (уточнено с заказчиком) — заполняется кнопкой
    # «Подтянуть цену» вместе с ценой. Нужна отдельно от price, т.к. выплата сборщику
    # считается не от полной стоимости, а только от части этих компонентов.
    bitrix_item_amount = models.DecimalField(
        'Сумма изделия (Bitrix)', max_digits=10, decimal_places=2, null=True, blank=True,
    )
    bitrix_assembly_percent = models.DecimalField(
        'Процент сборки, цеха, % (Bitrix)', max_digits=5, decimal_places=2, null=True, blank=True,
    )
    bitrix_installation_amount = models.DecimalField(
        'Монтаж (Bitrix)', max_digits=10, decimal_places=2, null=True, blank=True,
    )
    bitrix_additional_services_amount = models.DecimalField(
        'Доп. услуги (Bitrix)', max_digits=10, decimal_places=2, null=True, blank=True,
    )
    bitrix_lift_amount = models.DecimalField(
        'Подъём (Bitrix)', max_digits=10, decimal_places=2, null=True, blank=True,
    )
    bitrix_delivery_amount = models.DecimalField(
        'Доставка (Bitrix)', max_digits=10, decimal_places=2, null=True, blank=True,
    )

    comment = models.TextField('Комментарий/особые условия', blank=True)
    client_contact_name = models.CharField('ФИО клиента на объекте', max_length=255, blank=True)
    client_contact_phone = models.CharField('Телефон клиента', max_length=20, blank=True)

    status = models.CharField('Статус', max_length=30, choices=Status.choices, default=Status.NEW)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_orders',
        verbose_name='Создал',
    )
    collector = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='booked_orders',
        verbose_name='Сборщик',
    )
    booked_at = models.DateTimeField('Забронирована', null=True, blank=True)
    confirmed_at = models.DateTimeField('Подтверждена', null=True, blank=True)
    closed_at = models.DateTimeField('Закрыта', null=True, blank=True)

    class Meta:
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['deadline_at']),
        ]

    def __str__(self):
        return f'Заявка #{self.pk} — {self.furniture_type} ({self.get_status_display()})'

    @property
    def additional_works_total(self):
        return sum((w.price for w in self.additional_works.all()), start=0)

    @property
    def total_price(self):
        return self.price + self.additional_works_total

    @property
    def bitrix_assembly_amount(self):
        """Процент сборки (цеха) в деньгах = процент от суммы изделия."""
        if self.bitrix_item_amount is None or self.bitrix_assembly_percent is None:
            return None
        return (self.bitrix_item_amount * self.bitrix_assembly_percent / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def bitrix_total(self):
        """Итого = сумма всех компонентов из Bitrix24 (уточнено с заказчиком)."""
        assembly_amount = self.bitrix_assembly_amount
        if self.bitrix_item_amount is None or assembly_amount is None:
            return None
        return (
            self.bitrix_item_amount + assembly_amount
            + (self.bitrix_installation_amount or 0)
            + (self.bitrix_additional_services_amount or 0)
            + (self.bitrix_lift_amount or 0)
            + (self.bitrix_delivery_amount or 0)
        )

    @property
    def collector_payout_amount(self):
        """То, что получит сборщик = процент сборки (цеха) + монтаж + доп. услуги
        (уточнено с заказчиком — НЕ полная стоимость сделки). None, если разбивка
        из Bitrix24 не заполнена."""
        assembly_amount = self.bitrix_assembly_amount
        if assembly_amount is None:
            return None
        return (
            assembly_amount
            + (self.bitrix_installation_amount or 0)
            + (self.bitrix_additional_services_amount or 0)
        )

    @property
    def collector_payout_total(self):
        """Итоговая сумма к выплате сборщику: разбивка Bitrix24 (если есть) плюс
        доп. работы, обнаруженные на объекте (AdditionalWork). Если разбивки нет —
        используется total_price (старое поведение)."""
        base = self.collector_payout_amount
        if base is None:
            return self.total_price
        return base + self.additional_works_total

    @property
    def is_overdue(self):
        from django.utils import timezone

        open_statuses = (
            self.Status.CONFIRMED, self.Status.IN_PROGRESS,
            self.Status.REPORT_UPLOADED, self.Status.REJECTED_FOR_REWORK,
        )
        return self.status in open_statuses and self.deadline_at < timezone.now()


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history', verbose_name='Заявка')
    from_status = models.CharField(
        'Предыдущий статус', max_length=30, blank=True, choices=Order.Status.choices,
    )
    to_status = models.CharField('Новый статус', max_length=30, choices=Order.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Кто изменил',
    )
    comment = models.TextField('Комментарий', blank=True)
    created_at = models.DateTimeField('Дата изменения', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'История статуса заявки'
        verbose_name_plural = 'История статусов заявок'
