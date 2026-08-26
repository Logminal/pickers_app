from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.notifications.services import notify

from .models import Order, OrderStatusHistory


class OrderBookingError(Exception):
    pass


# Активные брони — те, что ещё не закрыты и не отменены; именно они занимают
# "слот" сборщика (п.10 ТЗ, открытый вопрос №3).
ACTIVE_BOOKING_STATUSES = (
    Order.Status.BOOKED, Order.Status.CONFIRMED, Order.Status.IN_PROGRESS,
    Order.Status.REPORT_UPLOADED, Order.Status.REJECTED_FOR_REWORK,
)


@transaction.atomic
def book_order(order_id, collector):
    """Первый отклик = бронирование (п.3.2 ТЗ).

    select_for_update блокирует строку заявки на время транзакции — если два
    сборщика жмут "Беру в работу" почти одновременно, вторая транзакция
    ждёт снятия блокировки первой и увидит уже актуальный статус.
    """
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.status != Order.Status.PUBLISHED:
        raise OrderBookingError('Заявка уже забронирована или недоступна')

    profile = getattr(collector, 'collector_profile', None)
    if profile and profile.is_blocked:
        if profile.blocked_until and profile.status != profile.Status.BLOCKED:
            raise OrderBookingError(f'Вы заблокированы до {profile.blocked_until:%d.%m.%Y %H:%M} — новые заявки брать нельзя.')
        raise OrderBookingError('Ваш аккаунт заблокирован — новые заявки брать нельзя.')

    active_count = Order.objects.filter(collector=collector, status__in=ACTIVE_BOOKING_STATUSES).count()
    if active_count >= settings.MAX_ACTIVE_BOOKINGS_PER_COLLECTOR:
        raise OrderBookingError(
            f'Нельзя забронировать больше {settings.MAX_ACTIVE_BOOKINGS_PER_COLLECTOR} '
            f'заявок одновременно — сначала завершите текущие.'
        )

    order.status = Order.Status.BOOKED
    order.collector = collector
    order.booked_at = timezone.now()
    order.save(update_fields=['status', 'collector', 'booked_at', 'updated_at'])

    OrderStatusHistory.objects.create(
        order=order,
        from_status=Order.Status.PUBLISHED,
        to_status=Order.Status.BOOKED,
        changed_by=collector,
    )

    if order.created_by:
        profile = getattr(collector, 'collector_profile', None)
        if profile:
            rating = f'{profile.average_rating:.1f}/5 ({profile.ratings_count} оценок)' if profile.average_rating else 'пока нет оценок'
            collector_info = f'{profile.full_name}, рейтинг {rating}'
        else:
            collector_info = str(collector)

        notify(
            order.created_by, event_type='order_booked',
            message=f'Заявка #{order.pk} забронирована сборщиком: {collector_info}. Требуется подтверждение.',
        )
    return order


@transaction.atomic
def confirm_booking(order_id, admin_user):
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.status != Order.Status.BOOKED:
        raise OrderBookingError('Заявка не в статусе "Забронирована"')

    order.status = Order.Status.CONFIRMED
    order.confirmed_at = timezone.now()
    order.save(update_fields=['status', 'confirmed_at', 'updated_at'])

    OrderStatusHistory.objects.create(
        order=order, from_status=Order.Status.BOOKED, to_status=Order.Status.CONFIRMED, changed_by=admin_user,
    )

    if order.collector:
        notify(
            order.collector, event_type='booking_confirmed',
            message=f'Бронь по заявке #{order.pk} подтверждена. Можно приступать к работе.',
        )
    return order


@transaction.atomic
def reject_booking(order_id, admin_user, reason=''):
    """Админ не подтверждает бронь (сомнения по сборщику) — просто возврат в пул, без блокировки (п.3.2)."""
    order = Order.objects.select_for_update().get(pk=order_id)

    if order.status != Order.Status.BOOKED:
        raise OrderBookingError('Заявка не в статусе "Забронирована"')

    collector = order.collector
    OrderStatusHistory.objects.create(
        order=order, from_status=order.status, to_status=Order.Status.PUBLISHED,
        changed_by=admin_user, comment=reason,
    )

    order.status = Order.Status.PUBLISHED
    order.collector = None
    order.booked_at = None
    order.save(update_fields=['status', 'collector', 'booked_at', 'updated_at'])

    if collector:
        notify(
            collector, event_type='booking_rejected',
            message=f'Бронь по заявке #{order.pk} не подтверждена администратором.' + (f' Причина: {reason}' if reason else ''),
        )
    return order


@transaction.atomic
def revoke_booking(order_id, admin_user, reason=''):
    """Сборщик пропал — снимаем заявку и возвращаем в пул (п.3.2).
    Блокировка самого сборщика — отдельный явный шаг (apps.collectors.services.block_collector),
    чтобы не блокировать случайно при обычном снятии брони.
    """
    order = Order.objects.select_for_update().get(pk=order_id)
    collector = order.collector

    OrderStatusHistory.objects.create(
        order=order, from_status=order.status, to_status=Order.Status.BOOKING_REVOKED,
        changed_by=admin_user, comment=reason,
    )

    order.status = Order.Status.PUBLISHED
    order.collector = None
    order.booked_at = None
    order.confirmed_at = None
    order.save(update_fields=['status', 'collector', 'booked_at', 'confirmed_at', 'updated_at'])

    if collector:
        notify(
            collector, event_type='booking_revoked',
            message=f'Бронь по заявке #{order.pk} снята администратором.' + (f' Причина: {reason}' if reason else ''),
        )
    return order


@transaction.atomic
def cancel_order(order_id, manager, reason=''):
    order = Order.objects.select_for_update().get(pk=order_id)
    from_status = order.status
    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status', 'updated_at'])
    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=Order.Status.CANCELLED, changed_by=manager, comment=reason,
    )
    if order.collector:
        notify(order.collector, event_type='order_cancelled', message=f'Заявка #{order.pk} отменена менеджером.')
    return order
