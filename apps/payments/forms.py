from django import forms

from .models import WithdrawalRequest


class WithdrawalRequestForm(forms.Form):
    method = forms.ChoiceField(
        label='Как получить выплату', choices=WithdrawalRequest.Method.choices, widget=forms.RadioSelect,
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


class RatingForm(forms.Form):
    score = forms.ChoiceField(
        label='Оценка', choices=[(i, f'{i} ★') for i in range(5, 0, -1)],
        widget=forms.RadioSelect,
    )
    deadline_met = forms.BooleanField(label='Срок соблюдён', required=False, initial=True)
    had_complaint = forms.BooleanField(label='Была рекламация от клиента', required=False)
    comment = forms.CharField(
        label='Комментарий', required=False, widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
    )
