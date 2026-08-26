from django.db import transaction
from django.utils import timezone

from apps.notifications.services import notify
from apps.orders.models import Order, OrderStatusHistory

from .forms import DEFAULT_CHECKLIST
from .models import Act, AdditionalWork, ChecklistItem, Photo, PhotoReport
from .video import compress_photo_report_video_async


@transaction.atomic
def submit_photo_report(
    order: Order, collector, slot_files: dict, checked_items: list, comment: str,
    additional_works: list | None = None, act_photo=None, video=None,
):
    """slot_files: {slot_id: UploadedFile}, checked_items: список отмеченных пунктов чек-листа.
    additional_works: [{'description': str, 'price': Decimal}, ...] — доп. работы сверх заявки.
    act_photo: фото подписанного акта приёма-передачи со стороны сборщика (п.4 ТЗ) —
    менеджер отдельно подтверждает его читаемость перед закрытием заявки.
    video: необязательный видеоотчёт — один файл на весь отчёт (не по слотам).
    """

    report, _ = PhotoReport.objects.get_or_create(order=order)
    report.comment = comment
    report.status = PhotoReport.Status.SUBMITTED
    report.submitted_at = timezone.now()
    if video is not None:
        report.video = video
    report.save()

    if video is not None:
        transaction.on_commit(lambda: compress_photo_report_video_async(report.pk))

    report.photos.all().delete()
    for slot_id, uploaded_file in slot_files.items():
        Photo.objects.create(report=report, slot_id=slot_id, file=uploaded_file)

    report.checklist_items.all().delete()
    for title in DEFAULT_CHECKLIST:
        ChecklistItem.objects.create(report=report, title=title, is_checked=title in checked_items)

    order.additional_works.all().delete()
    for work in (additional_works or []):
        AdditionalWork.objects.create(
            order=order, description=work['description'], price=work['price'], added_by=collector,
        )

    if act_photo is not None:
        # Новое фото — значит, читаемость нужно подтверждать заново, даже если
        # это доработка после отклонения и акт уже был подтверждён раньше.
        Act.objects.update_or_create(
            order=order,
            defaults={'file': act_photo, 'uploaded_by': collector, 'is_readable_confirmed': False},
        )

    from_status = order.status
    order.status = Order.Status.REPORT_UPLOADED
    order.save(update_fields=['status', 'updated_at'])
    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=Order.Status.REPORT_UPLOADED, changed_by=collector,
    )

    if order.created_by:
        notify(
            order.created_by, event_type='report_uploaded',
            message=f'Сборщик загрузил фотоотчёт по заявке #{order.pk}. Требуется проверка.',
        )
    return report


@transaction.atomic
def review_photo_report(order: Order, manager, accepted: bool, comment: str = '', manager_act_file=None):
    """manager_act_file: отдельный акт от менеджера — обязателен при приёме отчёта
    (см. Act.manager_act_file, п. «менеджер тоже должен прикрепить акт»)."""
    report = order.photo_report
    from_status = order.status

    if accepted:
        act = getattr(order, 'act', None)
        if manager_act_file is None and not (act and act.manager_act_file):
            raise ValueError('Для приёма отчёта нужно прикрепить акт от менеджера.')
        report.status = PhotoReport.Status.ACCEPTED
        order.status = Order.Status.ACCEPTED
    else:
        report.status = PhotoReport.Status.REJECTED
        report.manager_comment = comment
        order.status = Order.Status.REJECTED_FOR_REWORK

    report.save()
    order.save(update_fields=['status', 'updated_at'])
    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=order.status, changed_by=manager, comment=comment,
    )

    if accepted and manager_act_file is not None:
        act, _ = Act.objects.get_or_create(order=order)
        act.manager_act_file = manager_act_file
        act.manager_act_uploaded_at = timezone.now()
        act.save(update_fields=['manager_act_file', 'manager_act_uploaded_at', 'updated_at'])

    if order.collector:
        if accepted:
            notify(
                order.collector, event_type='report_accepted',
                message=f'Фотоотчёт по заявке #{order.pk} принят. Акт от менеджера доступен для скачивания.',
            )
        else:
            notify(
                order.collector, event_type='report_rejected',
                message=f'Фотоотчёт по заявке #{order.pk} отклонён на доработку.' + (f' Комментарий: {comment}' if comment else ''),
            )
    return report


@transaction.atomic
def close_order(order: Order, manager):
    """Без прикреплённого и подтверждённо-читаемого акта заявку нельзя закрыть (п.4 ТЗ)."""
    if not hasattr(order, 'act'):
        raise ValueError('Нельзя закрыть заявку без прикреплённого акта приёма-передачи')
    if not order.act.is_readable_confirmed:
        raise ValueError('Нельзя закрыть заявку: не подтверждена читаемость акта')
    if order.status != Order.Status.ACCEPTED:
        raise ValueError('Заявка должна быть принята менеджером перед закрытием')

    from_status = order.status
    order.status = Order.Status.CLOSED
    order.closed_at = timezone.now()
    order.save(update_fields=['status', 'closed_at', 'updated_at'])
    OrderStatusHistory.objects.create(
        order=order, from_status=from_status, to_status=Order.Status.CLOSED, changed_by=manager,
    )

    if order.collector:
        notify(
            order.collector, event_type='act_available',
            message=f'Заявка #{order.pk} закрыта. Акт приёма-передачи доступен для скачивания.',
        )

    from apps.payments.services import create_payment_record
    create_payment_record(order)

    return order
