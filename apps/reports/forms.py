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

    # Акт приёма-передачи (п.4 ТЗ) теперь прикрепляет сам сборщик — фото
    # подписанного бланка с объекта, а не отдельный шаг менеджера. Менеджер
    # по-прежнему подтверждает читаемость (или прикладывает свой файл, если
    # снимок не годится) на странице проверки отчёта.
    act_photo = forms.ImageField(
        label='Акт приёма-передачи (фото подписанного бланка)',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, slots, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for slot in slots:
            self.fields[f'slot_{slot.id}'] = forms.ImageField(
                label=slot.title, required=slot.is_required,
                widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
            )
        # act_photo должно быть в форме последним полем визуально — раз добавлено
        # в Meta класса раньше динамических слотов, переносим порядок явно.
        self.order_fields(list(self.fields.keys())[1:] + ['act_photo'])


# Доп. работы, обнаруженные на объекте сверх заявки (по образцу «Руки») —
# фиксированное число необязательных строк вместо динамического JS-формсета, для простоты MVP.
ADDITIONAL_WORK_ROWS = 3


class ActUploadForm(forms.Form):
    # Необязательно: обычно акт уже прикреплён сборщиком при сдаче фотоотчёта
    # (см. SlotPhotoForm.act_photo) — менеджеру нужно только подтвердить
    # читаемость. Файл можно заменить здесь же, если снимок сборщика не годится.
    act_file = forms.FileField(
        label='Файл акта (оставьте пустым, чтобы не менять уже прикреплённый)',
        required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
    )
    is_readable_confirmed = forms.BooleanField(
        label='Подтверждаю: акт заполнен по бланку, все поля разборчивы',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
