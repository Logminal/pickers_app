from django import template

register = template.Library()

# Единая семантика цвета статуса по всему приложению — заявки, анкеты, отчёты.
STATUS_COLOR_MAP = {
    # Order.Status
    'new': 'status-neutral',
    'published': 'status-neutral',
    'booked': 'status-warning',
    'confirmed': 'status-info',
    'in_progress': 'status-info',
    'report_uploaded': 'status-brand',
    'rejected_for_rework': 'status-danger',
    'accepted': 'status-brand',
    'closed': 'status-success',
    'cancelled': 'status-neutral',
    'booking_revoked': 'status-danger',
    'disputed': 'status-danger',
    # CollectorProfile.Status
    'draft': 'status-neutral',
    'under_review': 'status-warning',
    'blocked': 'status-danger',
    'rejected': 'status-danger',
    # PhotoReport.Status
    'submitted': 'status-brand',
}


@register.filter
def status_class(value):
    return STATUS_COLOR_MAP.get(value, 'status-neutral')


@register.filter
def get_item(dictionary, key):
    """Доступ к словарю по ключу-переменной в шаблоне: {{ mydict|get_item:key }}."""
    if not dictionary:
        return None
    return dictionary.get(key, key)
