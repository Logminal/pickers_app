from django import forms

from .models import ChecklistItem, PhotoReport

DEFAULT_CHECKLIST = [
    'Все модули собраны согласно схеме',
    'Фасады и ящики открываются/закрываются без перекоса',
    'Техника установлена и подключена (если входило в заявку)',
    'Мебель выровнена, устойчива',
    'Место убрано от мусора/упаковки',
]


class PhotoReportCommentForm(forms.ModelForm):
    class Meta:
        model = PhotoReport
        fields = ['comment']
        widgets = {'comment': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})}


class SlotPhotoForm(forms.Form):
    """Одно поле загрузки на слот — рендерится динамически в шаблоне по списку слотов."""

    def __init__(self, slots, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for slot in slots:
            self.fields[f'slot_{slot.id}'] = forms.ImageField(
                label=slot.title, required=slot.is_required,
                widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
            )


# Доп. работы, обнаруженные на объекте сверх заявки (по образцу «Руки») —
# фиксированное число необязательных строк вместо динамического JS-формсета, для простоты MVP.
ADDITIONAL_WORK_ROWS = 3


class ActUploadForm(forms.Form):
    act_file = forms.FileField(label='Файл акта', widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))
    is_readable_confirmed = forms.BooleanField(
        label='Подтверждаю: акт заполнен по бланку, все поля разборчивы',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
