from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notifications.services import notify
from apps.orders.models import Order

# Сколько времени даётся сборщику на выход на связь после подтверждения брони,
# прежде чем считать его "пропавшим" (открытый вопрос №2 из ТЗ — уточнить у заказчика,
# пока берём 24 часа как временное значение).
MISSING_COLLECTOR_GRACE_HOURS = 24


class Command(BaseCommand):
    """Раз в сутки на cron: помечает просроченные заявки и уведомляет менеджеров (п.6 ТЗ)."""

    help = 'Проверяет просрочку заявок и оповещает менеджеров/сборщиков'

    def handle(self, *args, **options):
        now = timezone.now()

        overdue_orders = Order.objects.filter(
            status__in=[Order.Status.IN_PROGRESS, Order.Status.CONFIRMED],
            deadline_at__lt=now,
        )
        for order in overdue_orders:
            if order.collector:
                notify(
                    order.collector,
                    event_type='deadline_overdue',
                    message=f'Просрочен срок сдачи по заявке #{order.pk}',
                )
            if order.created_by:
                notify(
                    order.created_by,
                    event_type='order_overdue',
                    message=f'Заявка #{order.pk} просрочена сборщиком',
                )

        self.stdout.write(self.style.SUCCESS(f'Проверено просроченных заявок: {overdue_orders.count()}'))
