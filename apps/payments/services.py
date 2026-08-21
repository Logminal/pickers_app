from django.db import transaction
from django.utils import timezone

from apps.notifications.services import notify
from apps.orders.models import Order

from .models import PaymentRecord, Rating


@transaction.atomic
def create_payment_record(order: Order):
    """Создаётся автоматически при закрытии заявки (п.5 ТЗ) — 'заявка закрыта -> сумма к выплате'.
    Сама выплата происходит вне системы, здесь только фиксация факта.
    """
    if not order.collector:
        return None

    record, _ = PaymentRecord.objects.get_or_create(
        order=order, defaults={'collector': order.collector, 'amount': order.total_price},
    )
    return record


@transaction.atomic
def mark_payment_paid(payment_record: PaymentRecord):
    payment_record.is_paid = True
    payment_record.paid_at = timezone.now()
    payment_record.save(update_fields=['is_paid', 'paid_at', 'updated_at'])

    notify(
        payment_record.collector, event_type='payment_marked_paid',
        message=f'Выплата по заявке #{payment_record.order_id} отмечена как произведённая: {payment_record.amount} ₽.',
    )
    return payment_record


@transaction.atomic
def rate_collector(order: Order, manager, score: int, deadline_met: bool, had_complaint: bool, comment: str = ''):
    if order.status != Order.Status.CLOSED:
        raise ValueError('Оценить сборщика можно только после закрытия заявки')
    if not order.collector:
        raise ValueError('У заявки нет сборщика')
    if not (1 <= score <= 5):
        raise ValueError('Оценка должна быть от 1 до 5')

    rating, created = Rating.objects.update_or_create(
        order=order,
        defaults={
            'collector': order.collector, 'rated_by': manager, 'score': score,
            'deadline_met': deadline_met, 'had_complaint': had_complaint, 'comment': comment,
        },
    )
    return rating
