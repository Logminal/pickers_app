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
    # CollectorProfileChangeRequest.Status / WithdrawalRequest.Status
    'pending': 'status-warning',
    'approved': 'status-success',
    'completed': 'status-success',
    # NotificationLog.Status
    'sent': 'status-success',
    'failed': 'status-danger',
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


@register.filter
def initials(full_name):
    """«Игорь Мельников» -> «ИМ» — для аватара-плашки без фото."""
    if not full_name:
        return '?'
    parts = str(full_name).split()
    letters = ''.join(p[0] for p in parts[:2] if p)
    return letters.upper() or '?'


@register.filter
def basename(file_field):
    """Имя файла без пути хранилища, для карточки вложения."""
    if not file_field:
        return ''
    name = getattr(file_field, 'name', str(file_field))
    return name.rsplit('/', 1)[-1]
