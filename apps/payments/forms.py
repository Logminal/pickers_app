from django import forms
from django.core.validators import FileExtensionValidator

from .models import RECEIPT_EXTENSIONS, WithdrawalRequest

MAX_RECEIPT_SIZE_MB = 8


def _validate_receipt_size(uploaded_file):
    max_bytes = MAX_RECEIPT_SIZE_MB * 1024 * 1024
    if uploaded_file.size > max_bytes:
        raise forms.ValidationError(f'Файл слишком большой — максимум {MAX_RECEIPT_SIZE_MB} МБ.')


class WithdrawalRequestForm(forms.Form):
    method = forms.ChoiceField(
        label='Как получить выплату', choices=WithdrawalRequest.Method.choices,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
    )
    requisite = forms.CharField(
        label='Номер карты или телефона', required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Заполните для перевода'}),
    )
    comment = forms.CharField(
        label='Комментарий (например, удобное время звонка)', required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
    )

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get('method')
        if method in (WithdrawalRequest.Method.PHONE_TRANSFER, WithdrawalRequest.Method.CARD_TRANSFER):
            if not cleaned.get('requisite'):
                raise forms.ValidationError('Укажите номер карты или телефона для перевода.')
        return cleaned


class WithdrawalReceiptForm(forms.Form):
    """Чек/квитанция о переводе — прикрепляется менеджером при завершении выплаты
    переводом (см. services.complete_withdrawal_request). Для 'лично в руки' не нужен,
    поэтому поле необязательное здесь — реальная обязательность проверяется в сервисе
    по способу получения конкретной заявки."""

    receipt = forms.FileField(
        label='Чек/квитанция о переводе', required=False,
        validators=[FileExtensionValidator(allowed_extensions=RECEIPT_EXTENSIONS), _validate_receipt_size],
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
    )


class RatingForm(forms.Form):
    score = forms.ChoiceField(
        label='Оценка', choices=[(i, f'{i} ★') for i in range(5, 0, -1)],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
    )
    deadline_met = forms.BooleanField(label='Срок соблюдён', required=False, initial=True)
    had_complaint = forms.BooleanField(label='Была рекламация от клиента', required=False)
    comment = forms.CharField(
        label='Комментарий', required=False, widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
    )
