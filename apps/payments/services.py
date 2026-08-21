from django.db import transaction
from django.utils import timezone

from apps.notifications.services import notify, notify_staff
from apps.orders.models import Order

from .models import PaymentRecord, Rating, WithdrawalRequest


@transaction.atomic
def create_payment_record(order: Order):
    """Создаётся автоматически при закрытии заявки (п.5 ТЗ) — 'заявка закрыта -> сумма к выплате'.
    Сама выплата происходит вне системы, здесь только фиксация факта.
    """
    if not order.collector:
        return None

    # Если из Bitrix24 подтянута разбивка стоимости — выплата сборщику считается
    # только от части (процент сборки + монтаж + доп. услуги), а не от полной
    # стоимости сделки (уточнено с заказчиком). Иначе — старое поведение.
    record, _ = PaymentRecord.objects.get_or_create(
        order=order, defaults={'collector': order.collector, 'amount': order.collector_payout_total},
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


class WithdrawalRequestError(Exception):
    pass


@transaction.atomic
def create_withdrawal_request(collector, method: str, requisite: str = '', comment: str = ''):
    """Сборщик запрашивает вывод накопленного баланса (неоплаченные PaymentRecord).
    Менеджеров уведомляем сразу — им нужно созвониться со сборщиком и договориться
    о переводе/встрече; сборщику приходит подтверждение, что заявка принята."""

    if WithdrawalRequest.objects.filter(collector=collector, status=WithdrawalRequest.Status.PENDING).exists():
        raise WithdrawalRequestError('У вас уже есть заявка на выплату, ожидающая обработки.')

    unpaid_records = PaymentRecord.objects.filter(collector=collector, is_paid=False)
    total = sum((r.amount for r in unpaid_records), start=0)
    if not unpaid_records.exists() or total <= 0:
        raise WithdrawalRequestError('На балансе нет средств к выплате.')

    request_obj = WithdrawalRequest.objects.create(
        collector=collector, amount=total, method=method, requisite=requisite, comment=comment,
    )
    request_obj.payment_records.set(unpaid_records)

    notify(
        collector, event_type='withdrawal_requested',
        message=f'Заявка на выплату {total} ₽ принята. Ожидайте звонка для уточнения деталей.',
    )

    profile = getattr(collector, 'collector_profile', None)
    name = profile.full_name if profile else str(collector)
    notify_staff(
        event_type='withdrawal_requested_staff',
        message=(
            f'Сборщик {name} ({collector.phone or "телефон не указан"}) запросил выплату '
            f'{total} ₽ — {request_obj.get_method_display()}. Нужно созвониться.'
        ),
    )

    return request_obj


@transaction.atomic
def complete_withdrawal_request(request_obj: WithdrawalRequest, manager):
    if request_obj.status != WithdrawalRequest.Status.PENDING:
        raise WithdrawalRequestError('Эта заявка уже обработана.')

    for record in request_obj.payment_records.all():
        record.is_paid = True
        record.paid_at = timezone.now()
        record.save(update_fields=['is_paid', 'paid_at', 'updated_at'])

    request_obj.status = WithdrawalRequest.Status.COMPLETED
    request_obj.handled_by = manager
    request_obj.completed_at = timezone.now()
    request_obj.save()

    notify(
        request_obj.collector, event_type='withdrawal_completed',
        message=f'Выплата {request_obj.amount} ₽ произведена.',
    )
    return request_obj


@transaction.atomic
def cancel_withdrawal_request(request_obj: WithdrawalRequest, manager, reason: str = ''):
    if request_obj.status != WithdrawalRequest.Status.PENDING:
        raise WithdrawalRequestError('Эта заявка уже обработана.')

    request_obj.status = WithdrawalRequest.Status.CANCELLED
    request_obj.handled_by = manager
    request_obj.completed_at = timezone.now()
    request_obj.save()

    notify(
        request_obj.collector, event_type='withdrawal_cancelled',
        message='Заявка на выплату отменена.' + (f' Причина: {reason}' if reason else ''),
    )
    return request_obj
