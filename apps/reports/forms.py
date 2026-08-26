from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

from .models import MANAGER_ACT_EXTENSIONS, VIDEO_EXTENSIONS, ChecklistItem, PhotoReport

DEFAULT_CHECKLIST = [
    'Все модули собраны согласно схеме',
    'Фасады и ящики открываются/закрываются без перекоса',
    'Техника установлена и подключена (если входило в заявку)',
    'Мебель выровнена, устойчива',
    'Место убрано от мусора/упаковки',
]

# Ограничения на загружаемые файлы (п. «не могли всякую хрень загружать») —
# помимо проверки типа/расширения, ограничиваем и размер.
MAX_PHOTO_SIZE_MB = 8
MAX_VIDEO_SIZE_MB = 150
MAX_MANAGER_ACT_SIZE_MB = 8


def _validate_max_size(max_mb):
    max_bytes = max_mb * 1024 * 1024

    def validator(uploaded_file):
        if uploaded_file.size > max_bytes:
            raise ValidationError(f'Файл слишком большой — максимум {max_mb} МБ.')

    return validator


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
        validators=[_validate_max_size(MAX_PHOTO_SIZE_MB)],
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
    )
    # Необязательное видео в дополнение к фотоотчёту — например, короткий обзор
    # объекта целиком, который неудобно передать отдельными фото по слотам.
    video = forms.FileField(
        label='Видеоотчёт (необязательно)', required=False,
        validators=[
            FileExtensionValidator(allowed_extensions=VIDEO_EXTENSIONS),
            _validate_max_size(MAX_VIDEO_SIZE_MB),
        ],
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
    )

    def __init__(self, slots, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for slot in slots:
            self.fields[f'slot_{slot.id}'] = forms.ImageField(
                label=slot.title, required=slot.is_required,
                validators=[_validate_max_size(MAX_PHOTO_SIZE_MB)],
                widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
            )
        # act_photo/video должны быть в форме последними полями визуально — раз
        # добавлены в Meta класса раньше динамических слотов, переносим порядок явно.
        self.order_fields(list(self.fields.keys())[2:] + ['act_photo', 'video'])


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


class ManagerActUploadForm(forms.Form):
    """Отдельный акт от менеджера (не путать с ActUploadForm.act_file — это замена
    фото сборщика). Обязателен при приёме отчёта, см. services.review_photo_report."""

    manager_act_file = forms.FileField(
        label='Акт от менеджера',
        validators=[
            FileExtensionValidator(allowed_extensions=MANAGER_ACT_EXTENSIONS),
            _validate_max_size(MAX_MANAGER_ACT_SIZE_MB),
        ],
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
    )
