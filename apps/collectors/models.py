from django.conf import settings
from django.db import models

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
    birth_place = models.CharField('Место рождения', max_length=255)
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

    class Meta:
        verbose_name = 'Анкета сборщика'
        verbose_name_plural = 'Анкеты сборщиков'

    def __str__(self):
        return f'{self.full_name} ({self.get_status_display()})'

    @property
    def average_rating(self):
        """Средний рейтинг по оценкам менеджера (п.5 ТЗ). None, если оценок ещё нет."""
        from django.db.models import Avg

        from apps.payments.models import Rating

        return Rating.objects.filter(collector=self.user).aggregate(avg=Avg('score'))['avg']

    @property
    def ratings_count(self):
        from apps.payments.models import Rating

        return Rating.objects.filter(collector=self.user).count()


class PassportData(TimeStampedModel):
    """Хранится отдельно от основной анкеты — доступ только у ограниченного круга (152-ФЗ, п.2.3)."""

    collector = models.OneToOneField(
        CollectorProfile, on_delete=models.CASCADE, related_name='passport', verbose_name='Сборщик',
    )

    series_number = models.CharField('Серия и номер паспорта', max_length=20)
    issued_by = models.CharField('Кем выдан', max_length=255)
    issue_date = models.DateField('Дата выдачи')
    division_code = models.CharField('Код подразделения', max_length=10)
    registration_address = models.TextField('Адрес регистрации')
    actual_address = models.TextField('Адрес фактического проживания')

    # Скан шифруется при записи и хранится вне MEDIA_ROOT — см. apps/collectors/storage.py.
    # Доступ только через PassportScanView (проверка роли + запись в PersonalDataAccessLog).
    scan_file = models.FileField('Скан паспорта', upload_to='%Y/%m/', storage=EncryptedPrivateStorage())

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
