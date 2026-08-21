from django.core.management.base import BaseCommand

from apps.dictionaries.models import FurnitureType
from apps.reports.models import PhotoSlotDefinition, PhotoSlotTemplate

# (название слота, обязателен ли)
KITCHEN_SLOTS = [
    ('Общий вид кухни целиком (ракурс 1)', True),
    ('Общий вид кухни целиком (ракурс 2)', True),
    ('Модуль крупным планом с открытыми фасадами/ящиками', True),
    ('Встроенная техника после установки/подключения', True),
    ('Столешница и мойка/смеситель', True),
    ('Примыкания — стыки со стеной, потолком, плинтуса', True),
    ('Убранное рабочее место', True),
    # Опциональные слоты контроля — по образцу сервиса «Руки»
    ('Сборщик в рабочей форме на объекте', False),
    ('Инструмент на подложке', False),
]


class Command(BaseCommand):
    """Разовый сид базового набора слотов фото для кухни (п.4 ТЗ).
    Наборы для других типов мебели — открытый вопрос №4 из ТЗ, добавлять по мере уточнения.
    Идемпотентна: можно перезапускать при добавлении новых слотов в KITCHEN_SLOTS.
    """

    help = 'Создаёт/дополняет шаблон фотоотчёта для кухни базовым набором слотов'

    def handle(self, *args, **options):
        template, _ = PhotoSlotTemplate.objects.get_or_create(name='Кухня — стандартный набор')

        for order, (title, is_required) in enumerate(KITCHEN_SLOTS):
            slot, created = PhotoSlotDefinition.objects.get_or_create(
                template=template, title=title, defaults={'is_required': is_required, 'order': order},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Добавлен слот: {title}'))

        furniture_type, _ = FurnitureType.objects.get_or_create(name='Кухня')
        furniture_type.photo_slots_template = template
        furniture_type.save()
        self.stdout.write(self.style.SUCCESS(f'Тип мебели "{furniture_type}" привязан к шаблону'))
