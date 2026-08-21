from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class PhotoSlotTemplate(models.Model):
    """Набор слотов фото для типа мебели (п.10 ТЗ, вопрос №4 — пока один набор для кухни)."""

    name = models.CharField('Название', max_length=100)

    class Meta:
        verbose_name = 'Шаблон фотоотчёта'
        verbose_name_plural = 'Шаблоны фотоотчётов'

    def __str__(self):
        return self.name


class PhotoSlotDefinition(models.Model):
    """Один слот в шаблоне: 'Общий вид', 'Столешница и мойка' и т.д. (п.4 ТЗ)."""

    template = models.ForeignKey(
        PhotoSlotTemplate, on_delete=models.CASCADE, related_name='slots', verbose_name='Шаблон',
    )
    title = models.CharField('Название слота', max_length=150)
    is_required = models.BooleanField('Обязателен', default=True)
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['order']
        verbose_name = 'Слот фото'
        verbose_name_plural = 'Слоты фото'

    def __str__(self):
        return self.title


class PhotoReport(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        SUBMITTED = 'submitted', 'Загружен'
        ACCEPTED = 'accepted', 'Принят менеджером'
        REJECTED = 'rejected', 'Отклонён (доработка)'

    order = models.OneToOneField(
        'orders.Order', on_delete=models.CASCADE, related_name='photo_report', verbose_name='Заявка',
    )
    status = models.CharField('Статус', max_length=20, choices=Status.choices, default=Status.DRAFT)
    comment = models.TextField('Комментарий сборщика', blank=True)
    manager_comment = models.TextField('Комментарий менеджера', blank=True)
    submitted_at = models.DateTimeField('Дата загрузки', null=True, blank=True)
    geolocation_lat = models.DecimalField('Широта', max_digits=9, decimal_places=6, null=True, blank=True)
    geolocation_lng = models.DecimalField('Долгота', max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name = 'Фотоотчёт'
        verbose_name_plural = 'Фотоотчёты'

    def __str__(self):
        return f'Фотоотчёт по заявке #{self.order_id}'


class Photo(TimeStampedModel):
    """Фото, привязанное к конкретному слоту отчёта. Файл хранится в приватном storage."""

    report = models.ForeignKey(PhotoReport, on_delete=models.CASCADE, related_name='photos', verbose_name='Отчёт')
    slot = models.ForeignKey(
        PhotoSlotDefinition, on_delete=models.PROTECT, related_name='photos', verbose_name='Слот',
    )
    file = models.ImageField('Файл', upload_to='reports/%Y/%m/')

    class Meta:
        verbose_name = 'Фото'
        verbose_name_plural = 'Фото'


class ChecklistItem(models.Model):
    """Пункт чек-листа перед сдачей (п.4 ТЗ)."""

    report = models.ForeignKey(
        PhotoReport, on_delete=models.CASCADE, related_name='checklist_items', verbose_name='Отчёт',
    )
    title = models.CharField('Пункт', max_length=200)
    is_checked = models.BooleanField('Отмечен', default=False)

    class Meta:
        verbose_name = 'Пункт чек-листа'
        verbose_name_plural = 'Чек-лист'

    def __str__(self):
        return self.title


class Act(TimeStampedModel):
    """Акт приёма-передачи, прикрепляемый менеджером (п.4 ТЗ).

    По образцу сервиса «Руки»: акт должен быть заполнен по фирменному бланку
    (FurnitureType.act_template_file) и читаем — это подтверждается чекбоксом
    при загрузке, а не автоматическим OCR (избыточно для MVP).
    """

    order = models.OneToOneField('orders.Order', on_delete=models.CASCADE, related_name='act', verbose_name='Заявка')
    file = models.FileField('Файл акта', upload_to='acts/%Y/%m/')
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Загрузил',
    )
    is_readable_confirmed = models.BooleanField(
        'Подтверждена читаемость', default=False,
        help_text='Менеджер подтвердил, что все поля акта заполнены и разборчивы',
    )

    class Meta:
        verbose_name = 'Акт приёма-передачи'
        verbose_name_plural = 'Акты приёма-передачи'

    def __str__(self):
        return f'Акт по заявке #{self.order_id}'


class AdditionalWork(TimeStampedModel):
    """Доп. работы, обнаруженные на объекте сверх исходной заявки — с ценой (по образцу «Руки»)."""

    order = models.ForeignKey(
        'orders.Order', on_delete=models.CASCADE, related_name='additional_works', verbose_name='Заявка',
    )
    description = models.CharField('Описание работы', max_length=255)
    price = models.DecimalField('Стоимость', max_digits=10, decimal_places=2)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Добавил',
    )

    class Meta:
        verbose_name = 'Дополнительная работа'
        verbose_name_plural = 'Дополнительные работы'

    def __str__(self):
        return f'{self.description} — {self.price} ₽ (заявка #{self.order_id})'
