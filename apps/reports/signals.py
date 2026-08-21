from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import AdditionalWork


def _sync_payment_record(order):
    """Держит сумму к выплате в актуальном состоянии, когда доп. работы
    добавляются/меняются/удаляются уже после закрытия заявки. Если выплата уже
    отмечена произведённой — не трогаем: деньги фактически переданы, расхождение
    нужно решать вручную, а не переписывать факт задним числом.

    Запрашиваем PaymentRecord отдельным запросом, а не через order.payment_record —
    обратная OneToOne-связь кэшируется на объекте order, и если тот же Python-объект
    order уже использовался до отметки is_paid=True, кэш покажет устаревшее значение.
    """
    from apps.payments.models import PaymentRecord

    record = PaymentRecord.objects.filter(order=order).first()
    if record is None or record.is_paid:
        return
    new_amount = order.collector_payout_total
    if record.amount != new_amount:
        record.amount = new_amount
        record.save(update_fields=['amount', 'updated_at'])


@receiver(post_save, sender=AdditionalWork)
def additional_work_saved(sender, instance, **kwargs):
    _sync_payment_record(instance.order)


@receiver(post_delete, sender=AdditionalWork)
def additional_work_deleted(sender, instance, **kwargs):
    _sync_payment_record(instance.order)
