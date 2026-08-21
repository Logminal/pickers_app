from django.db import models


class FurnitureType(models.Model):
    """Тип мебели: кухня, шкаф-купе, гардеробная и т.д."""

    name = models.CharField('Название', max_length=100, unique=True)
    photo_slots_template = models.ForeignKey(
        'reports.PhotoSlotTemplate', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='furniture_types', verbose_name='Шаблон фотоотчёта',
        help_text='Набор обязательных фото для этого типа мебели (п.10 ТЗ, вопрос №4)',
    )
    act_template_file = models.FileField(
        'Бланк акта приёма-передачи', upload_to='dictionaries/act_templates/', blank=True, null=True,
        help_text='Пустой бланк акта для этого типа мебели — менеджер заполняет и прикладывает по нему',
    )

    class Meta:
        verbose_name = 'Тип мебели'
        verbose_name_plural = 'Типы мебели'

    def __str__(self):
        return self.name


class Region(models.Model):
    name = models.CharField('Название', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Регион'
        verbose_name_plural = 'Регионы'

    def __str__(self):
        return self.name


class Specialization(models.Model):
    """Специализация сборщика (мультивыбор в анкете)."""

    name = models.CharField('Название', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Специализация'
        verbose_name_plural = 'Специализации'

    def __str__(self):
        return self.name


class PriceListItem(models.Model):
    """Прайс-лист: ставка за модуль/тип работы для расчётной стоимости заявки."""

    furniture_type = models.ForeignKey(
        FurnitureType, on_delete=models.CASCADE, related_name='price_items', verbose_name='Тип мебели',
    )
    name = models.CharField('Название позиции', max_length=150)
    price_per_unit = models.DecimalField('Цена за единицу', max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Позиция прайс-листа'
        verbose_name_plural = 'Прайс-лист'

    def __str__(self):
        return f'{self.name} — {self.price_per_unit} ₽'
