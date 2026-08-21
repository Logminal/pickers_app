from django.db import transaction
from django.utils import timezone

from apps.notifications.services import notify

from .models import CollectorProfile, CollectorProfileChangeRequest, PaymentDetails


@transaction.atomic
def block_collector(profile: CollectorProfile, reason: str = ''):
    """Блокировка сборщика (п.3.2 ТЗ) — без возможности откликаться на новые заявки."""
    profile.status = CollectorProfile.Status.BLOCKED
    if reason:
        profile.rejection_reason = reason
    profile.save(update_fields=['status', 'rejection_reason', 'updated_at'])
    return profile


@transaction.atomic
def unblock_collector(profile: CollectorProfile):
    profile.status = CollectorProfile.Status.CONFIRMED
    profile.save(update_fields=['status', 'updated_at'])
    return profile


def _current_field_values(profile: CollectorProfile, payment: PaymentDetails):
    return {
        'user.phone': profile.user.phone,
        'user.email': profile.user.email,
        'profile.region': profile.region_id,
        'profile.specializations': set(profile.specializations.values_list('id', flat=True)),
        'profile.experience_years': profile.experience_years,
        'profile.has_own_tools': profile.has_own_tools,
        'profile.tools_list': profile.tools_list,
        'profile.has_car': profile.has_car,
        'profile.willing_to_travel': profile.willing_to_travel,
        'profile.emergency_contact': profile.emergency_contact,
        'payment.method': payment.method,
        'payment.card_or_account_number': payment.card_or_account_number,
        'payment.sbp_phone': payment.sbp_phone,
        'payment.cash_pickup_address': payment.cash_pickup_address,
        'payment.cash_pickup_time': payment.cash_pickup_time,
        'payment.cash_pickup_contact': payment.cash_pickup_contact,
    }


@transaction.atomic
def submit_profile_change_request(profile: CollectorProfile, data: dict):
    """Считает дифф между текущими данными и предложенными сборщиком.
    Возвращает None, если реальных изменений нет (не создаёт пустую заявку)."""

    payment, _ = PaymentDetails.objects.get_or_create(collector=profile)
    current = _current_field_values(profile, payment)

    proposed = {
        'user.phone': data['phone'],
        'user.email': data.get('email', ''),
        'profile.region': data['region'].id if data.get('region') else None,
        'profile.specializations': set(s.id for s in data.get('specializations', [])),
        'profile.experience_years': data['experience_years'],
        'profile.has_own_tools': data['has_own_tools'],
        'profile.tools_list': data.get('tools_list', ''),
        'profile.has_car': data['has_car'],
        'profile.willing_to_travel': data['willing_to_travel'],
        'profile.emergency_contact': data.get('emergency_contact', ''),
        'payment.method': data['payment_method'],
        'payment.card_or_account_number': data.get('card_or_account_number', ''),
        'payment.sbp_phone': data.get('sbp_phone', ''),
        'payment.cash_pickup_address': data.get('cash_pickup_address', ''),
        'payment.cash_pickup_time': data.get('cash_pickup_time', ''),
        'payment.cash_pickup_contact': data.get('cash_pickup_contact', ''),
    }

    changes = {}
    for key, new_value in proposed.items():
        old_value = current[key]
        if key == 'profile.specializations':
            if new_value != old_value:
                changes[key] = sorted(new_value)
        elif new_value != old_value:
            changes[key] = new_value

    if not changes:
        return None

    return CollectorProfileChangeRequest.objects.create(profile=profile, changes=changes)


@transaction.atomic
def approve_change_request(change_request: CollectorProfileChangeRequest, reviewer):
    profile = change_request.profile
    user = profile.user
    payment, _ = PaymentDetails.objects.get_or_create(collector=profile)

    for key, value in change_request.changes.items():
        target, field = key.split('.', 1)
        if target == 'user':
            setattr(user, field, value)
        elif target == 'profile':
            if field == 'specializations':
                profile.specializations.set(value)
            elif field == 'region':
                profile.region_id = value
            else:
                setattr(profile, field, value)
        elif target == 'payment':
            setattr(payment, field, value)

    user.save()
    profile.save()
    payment.save()

    change_request.status = CollectorProfileChangeRequest.Status.APPROVED
    change_request.reviewed_by = reviewer
    change_request.reviewed_at = timezone.now()
    change_request.save()

    notify(user, event_type='profile_change_approved', message='Изменения в вашей анкете подтверждены менеджером.')
    return change_request


@transaction.atomic
def reject_change_request(change_request: CollectorProfileChangeRequest, reviewer, reason: str = ''):
    change_request.status = CollectorProfileChangeRequest.Status.REJECTED
    change_request.reviewed_by = reviewer
    change_request.reviewed_at = timezone.now()
    change_request.review_comment = reason
    change_request.save()

    notify(
        change_request.profile.user, event_type='profile_change_rejected',
        message='Изменения в вашей анкете отклонены менеджером.' + (f' Причина: {reason}' if reason else ''),
    )
    return change_request
