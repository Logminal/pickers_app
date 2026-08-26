from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

from .storage import EncryptedPrivateStorage


class CollectorProfile(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        UNDER_REVIEW = 'under_review', 'На проверке'
        CONFIRMED = 'confirmed', 'Подтверждён'
        REJECTED = 'rejected', 'Отклонён'
        BLOCKED = 'blocked', 'Заблокирован'

    class TaxStatus(models.TextChoices):
        INDIVIDUAL = 'individual', 'Физлицо'
        SELF_EMPLOYED = 'self_employed', 'Самозанятый (НПД)'
        SOLE_PROPRIETOR = 'sole_proprietor', 'ИП'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='collector_profile',
        verbose_name='Пользователь',
    )

    full_name = models.CharField('ФИО', max_length=255)
    birth_date = models.DateField('Дата рождения')
    birth_place = models.CharField('Место рождения', max_length=255, blank=True)
    profile_photo = models.ImageField('Фото профиля', upload_to='collectors/profile_photos/')

    status = models.CharField('Статус анкеты', max_length=20, choices=Status.choices, default=Status.DRAFT)
    rejection_reason = models.TextField('Причина отклонения', blank=True)

    tax_status = models.CharField(
        'Налоговый статус', max_length=20, choices=TaxStatus.choices, default=TaxStatus.INDIVIDUAL,
    )
    inn = models.CharField('ИНН', max_length=12, blank=True)
    ogrnip = models.CharField('ОГРНИП', max_length=15, blank=True)
    npd_certificate = models.FileField('Справка НПД', upload_to='collectors/npd/', blank=True, null=True)

    specializations = models.ManyToManyField(
        'dictionaries.Specialization', related_name='collectors', blank=True, verbose_name='Специализации',
    )
    experience_years = models.PositiveSmallIntegerField('Стаж работы (лет)', default=0)
    has_own_tools = models.BooleanField('Есть свой инструмент', default=False)
    tools_list = models.TextField('Список инструмента', blank=True)
    has_car = models.BooleanField('Есть автомобиль', default=False)
    region = models.ForeignKey(
        'dictionaries.Region', on_delete=models.SET_NULL, null=True, related_name='collectors',
        verbose_name='Регион',
    )
    willing_to_travel = models.BooleanField('Готов к выездам в другие районы', default=False)

    emergency_contact = models.CharField('Контакт для экстренной связи', max_length=255, blank=True)

    personal_data_consent_given_at = models.DateTimeField('Согласие на ПДн дано', null=True, blank=True)
    personal_data_consent_ip = models.GenericIPAddressField('IP при согласии на ПДн', null=True, blank=True)

    # Временная блокировка — заявки брать нельзя, пока не истечёт срок (см. is_blocked).
    # Постоянная блокировка по-прежнему выражается через status=BLOCKED (см. services.block_collector).
    blocked_until = models.DateTimeField('Заблокирован до', null=True, blank=True)
    block_reason = models.TextField('Причина блокировки', blank=True)

    # Ручная корректировка итогового рейтинга администратором — если задана,
    # полностью подменяет собой average_rating (не усредняется с ним).
    rating_override = models.DecimalField(
        'Ручная корректировка рейтинга', max_digits=3, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('5'))],
    )

    class Meta:
        verbose_name = 'Анкета сборщика'
        verbose_name_plural = 'Анкеты сборщиков'

    def __str__(self):
        return f'{self.full_name} ({self.get_status_display()})'

    @property
    def average_rating(self):
        """Средний рейтинг по оценкам менеджера (п.5 ТЗ), если только не задана
        ручная корректировка администратором (rating_override) — тогда она в приоритете.
        None, если оценок ещё нет и корректировка не задана."""
        if self.rating_override is not None:
            return self.rating_override

        from django.db.models import Avg

        from apps.payments.models import Rating

        return Rating.objects.filter(collector=self.user).aggregate(avg=Avg('score'))['avg']

    @property
    def ratings_count(self):
        from apps.payments.models import Rating

        return Rating.objects.filter(collector=self.user).count()

    @property
    def is_blocked(self):
        """Заблокирован — постоянно (status=BLOCKED) либо временно (blocked_until в будущем)."""
        if self.status == self.Status.BLOCKED:
            return True
        return bool(self.blocked_until and self.blocked_until > timezone.now())


class PassportData(TimeStampedModel):
    """Хранится отдельно от основной анкеты — доступ только у ограниченного круга (152-ФЗ, п.2.3)."""

    collector = models.OneToOneField(
        CollectorProfile, on_delete=models.CASCADE, related_name='passport', verbose_name='Сборщик',
    )

    series_number = models.CharField('Серия и номер паспорта', max_length=20, blank=True)
    issued_by = models.CharField('Кем выдан', max_length=255, blank=True)
    issue_date = models.DateField('Дата выдачи', null=True, blank=True)
    division_code = models.CharField('Код подразделения', max_length=10, blank=True)
    registration_address = models.TextField('Адрес регистрации', blank=True)
    actual_address = models.TextField('Адрес фактического проживания', blank=True)

    # Сканы шифруются при записи и хранятся вне MEDIA_ROOT — см. apps/collectors/storage.py.
    # Доступ только через PassportScanView (проверка роли + запись в PersonalDataAccessLog).
    # Разворот с фото и страница с пропиской — отдельные фото (сборщику неудобно и часто
    # нечитаемо снимать обе страницы паспорта одним кадром).
    scan_file = models.FileField('Скан паспорта (разворот с фото)', upload_to='%Y/%m/', storage=EncryptedPrivateStorage())
    registration_scan_file = models.FileField(
        'Скан страницы с пропиской', upload_to='%Y/%m/', storage=EncryptedPrivateStorage(), default='',
    )

    class Meta:
        verbose_name = 'Паспортные данные'
        verbose_name_plural = 'Паспортные данные'

    def __str__(self):
        return f'Паспорт: {self.collector.full_name}'


class PaymentDetails(TimeStampedModel):
    class Method(models.TextChoices):
        CARD = 'card', 'Банковская карта / реквизиты'
        SBP = 'sbp', 'СБП'
        CASH = 'cash', 'Наличные'

    collector = models.OneToOneField(
        CollectorProfile, on_delete=models.CASCADE, related_name='payment_details', verbose_name='Сборщик',
    )
    method = models.CharField('Способ оплаты', max_length=20, choices=Method.choices, default=Method.CARD)

    card_or_account_number = models.CharField('Номер карты/реквизиты', max_length=34, blank=True)
    sbp_phone = models.CharField('СБП-номер телефона', max_length=20, blank=True)

    cash_pickup_address = models.CharField('Адрес для передачи наличных', max_length=255, blank=True)
    cash_pickup_time = models.CharField('Желаемое время передачи', max_length=100, blank=True)
    cash_pickup_contact = models.CharField('Контакт для передачи', max_length=100, blank=True)

    class Meta:
        verbose_name = 'Реквизиты для оплаты'
        verbose_name_plural = 'Реквизиты для оплаты'

    def __str__(self):
        return f'Реквизиты: {self.collector.full_name}'


class CollectorProfileChangeRequest(TimeStampedModel):
    """Сборщик меняет свои данные сам, но изменения применяются только после
    подтверждения менеджером/админом — правки не идут в анкету напрямую."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'На рассмотрении'
        APPROVED = 'approved', 'Одобрено'
        REJECTED = 'rejected', 'Отклонено'

    profile = models.ForeignKey(
        CollectorProfile, on_delete=models.CASCADE, related_name='change_requests', verbose_name='Анкета',
    )
    changes = models.JSONField('Предлагаемые изменения', help_text='{"поле": "новое значение"}')
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_change_requests', verbose_name='Кто рассмотрел',
    )
    reviewed_at = models.DateTimeField('Дата рассмотрения', null=True, blank=True)
    review_comment = models.TextField('Комментарий рассмотрения', blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заявка на изменение анкеты'
        verbose_name_plural = 'Заявки на изменение анкет'

    def __str__(self):
        return f'Изменение анкеты «{self.profile.full_name}» ({self.get_status_display()})'


class CollectorNote(TimeStampedModel):
    """Внутренняя заметка менеджера о сборщике — не привязана к конкретной заявке,
    видна только менеджерам/админам (страница профиля сборщика и так недоступна
    больше никому). Для памяти "кто это такой", а не для оценки качества работы —
    для этого есть Rating."""

    profile = models.ForeignKey(
        CollectorProfile, on_delete=models.CASCADE, related_name='notes', verbose_name='Сборщик',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Автор',
    )
    text = models.TextField('Текст заметки')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Заметка о сборщике'
        verbose_name_plural = 'Заметки о сборщиках'

    def __str__(self):
        return f'Заметка о {self.profile.full_name} от {self.author}'
