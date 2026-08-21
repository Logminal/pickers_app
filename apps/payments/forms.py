from django import forms


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
