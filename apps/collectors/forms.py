from django import forms
from django.contrib.auth import get_user_model

from .models import CollectorProfile, PassportData, PaymentDetails

User = get_user_model()


class CollectorRegistrationForm(forms.Form):
    """Регистрация сборщика (п.2.1 ТЗ) — упрощённая версия для MVP:
    ключевые поля одной формой, без разбивки на шаги.
    """

    # Учётные данные
    username = forms.CharField(label='Логин')
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput)
    phone = forms.CharField(label='Номер телефона')
    email = forms.EmailField(label='Email', required=False)

    # Личные данные
    full_name = forms.CharField(label='ФИО (полностью, как в паспорте)')
    birth_date = forms.DateField(label='Дата рождения', widget=forms.DateInput(attrs={'type': 'date'}))
    birth_place = forms.CharField(label='Место рождения')
    profile_photo = forms.ImageField(label='Фото профиля (селфи)')

    # Паспортные данные
    passport_series_number = forms.CharField(label='Серия и номер паспорта')
    passport_issued_by = forms.CharField(label='Кем выдан')
    passport_issue_date = forms.DateField(label='Дата выдачи', widget=forms.DateInput(attrs={'type': 'date'}))
    passport_division_code = forms.CharField(label='Код подразделения')
    passport_registration_address = forms.CharField(label='Адрес регистрации', widget=forms.Textarea(attrs={'rows': 2}))
    passport_actual_address = forms.CharField(label='Адрес фактического проживания', widget=forms.Textarea(attrs={'rows': 2}))
    passport_scan = forms.FileField(label='Скан паспорта (разворот + прописка)')

    # Налоговый статус
    tax_status = forms.ChoiceField(label='Статус', choices=CollectorProfile.TaxStatus.choices)
    inn = forms.CharField(label='ИНН (для самозанятых)', required=False)
    ogrnip = forms.CharField(label='ОГРНИП (для ИП)', required=False)
    personal_data_consent = forms.BooleanField(label='Согласен на обработку персональных данных')
    offer_accepted = forms.BooleanField(
        label='Принимаю условия оферты', error_messages={'required': 'Необходимо принять условия оферты'},
    )

    # Реквизиты
    payment_method = forms.ChoiceField(label='Способ получения оплаты', choices=PaymentDetails.Method.choices)
    card_or_account_number = forms.CharField(label='Номер карты/реквизиты', required=False)
    sbp_phone = forms.CharField(label='СБП-номер телефона', required=False)
    cash_pickup_address = forms.CharField(label='Адрес для передачи наличных', required=False)

    # Профессиональные данные
    experience_years = forms.IntegerField(label='Стаж работы (лет)', min_value=0, initial=0)
    has_own_tools = forms.BooleanField(label='Есть свой инструмент', required=False)
    has_car = forms.BooleanField(label='Есть автомобиль', required=False)
    region = forms.ModelChoiceField(label='Регион работы', queryset=None, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.dictionaries.models import Region
        self.fields['region'].queryset = Region.objects.all()
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            if isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs['class'] = (existing + ' form-check-input').strip()
            else:
                field.widget.attrs['class'] = (existing + ' form-control').strip()

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Этот логин уже занят')
        return username

    def clean_phone(self):
        digits = ''.join(ch for ch in self.cleaned_data['phone'] if ch.isdigit())
        if digits and digits[0] == '8':
            digits = '7' + digits[1:]
        if len(digits) != 11 or digits[0] != '7':
            raise forms.ValidationError('Введите номер телефона в формате +7 (999) 999-99-99')

        phone = '+7 (' + digits[1:4] + ') ' + digits[4:7] + '-' + digits[7:9] + '-' + digits[9:11]
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError('Этот телефон уже зарегистрирован')
        return phone

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('personal_data_consent'):
            raise forms.ValidationError('Необходимо согласие на обработку персональных данных')
        return cleaned

    def save(self, request):
        data = self.cleaned_data

        user = User.objects.create_user(
            username=data['username'],
            password=data['password'],
            email=data.get('email', ''),
            phone=data['phone'],
            role=User.Role.COLLECTOR,
        )

        from django.utils import timezone
        collector = CollectorProfile.objects.create(
            user=user,
            full_name=data['full_name'],
            birth_date=data['birth_date'],
            birth_place=data['birth_place'],
            profile_photo=data['profile_photo'],
            status=CollectorProfile.Status.UNDER_REVIEW,
            tax_status=data['tax_status'],
            inn=data.get('inn', ''),
            ogrnip=data.get('ogrnip', ''),
            experience_years=data['experience_years'],
            has_own_tools=data['has_own_tools'],
            has_car=data['has_car'],
            region=data.get('region'),
            personal_data_consent_given_at=timezone.now(),
            personal_data_consent_ip=request.META.get('REMOTE_ADDR'),
        )

        PassportData.objects.create(
            collector=collector,
            series_number=data['passport_series_number'],
            issued_by=data['passport_issued_by'],
            issue_date=data['passport_issue_date'],
            division_code=data['passport_division_code'],
            registration_address=data['passport_registration_address'],
            actual_address=data['passport_actual_address'],
            scan_file=data['passport_scan'],
        )

        PaymentDetails.objects.create(
            collector=collector,
            method=data['payment_method'],
            card_or_account_number=data.get('card_or_account_number', ''),
            sbp_phone=data.get('sbp_phone', ''),
            cash_pickup_address=data.get('cash_pickup_address', ''),
        )

        return user


# Человекочитаемые подписи для отображения диффа менеджеру при рассмотрении заявки на изменение.
CHANGE_FIELD_LABELS = {
    'user.phone': 'Телефон',
    'user.email': 'Email',
    'profile.region': 'Регион работы',
    'profile.specializations': 'Специализации',
    'profile.experience_years': 'Стаж работы (лет)',
    'profile.has_own_tools': 'Есть свой инструмент',
    'profile.tools_list': 'Список инструмента',
    'profile.has_car': 'Есть автомобиль',
    'profile.willing_to_travel': 'Готов к выездам в другие районы',
    'profile.emergency_contact': 'Контакт для экстренной связи',
    'payment.method': 'Способ получения оплаты',
    'payment.card_or_account_number': 'Номер карты/реквизиты',
    'payment.sbp_phone': 'СБП-номер телефона',
    'payment.cash_pickup_address': 'Адрес для передачи наличных',
    'payment.cash_pickup_time': 'Желаемое время передачи',
    'payment.cash_pickup_contact': 'Контакт для передачи',
}


class ProfileEditForm(forms.Form):
    """Самостоятельное редактирование сборщиком своих данных — контакты,
    профессиональные данные, реквизиты. Паспортные данные и ФИО тут не меняются:
    это идентификационные поля, требующие отдельной переверификации, не входят в MVP.
    """

    phone = forms.CharField(label='Телефон')
    email = forms.EmailField(label='Email', required=False)

    region = forms.ModelChoiceField(label='Регион работы', queryset=None, required=False)
    specializations = forms.ModelMultipleChoiceField(
        label='Специализации', queryset=None, required=False, widget=forms.CheckboxSelectMultiple,
    )
    experience_years = forms.IntegerField(label='Стаж работы (лет)', min_value=0)
    has_own_tools = forms.BooleanField(label='Есть свой инструмент', required=False)
    tools_list = forms.CharField(label='Список инструмента', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    has_car = forms.BooleanField(label='Есть автомобиль', required=False)
    willing_to_travel = forms.BooleanField(label='Готов к выездам в другие районы', required=False)
    emergency_contact = forms.CharField(label='Контакт для экстренной связи', required=False)

    payment_method = forms.ChoiceField(label='Способ получения оплаты', choices=PaymentDetails.Method.choices)
    card_or_account_number = forms.CharField(label='Номер карты/реквизиты', required=False)
    sbp_phone = forms.CharField(label='СБП-номер телефона', required=False)
    cash_pickup_address = forms.CharField(label='Адрес для передачи наличных', required=False)
    cash_pickup_time = forms.CharField(label='Желаемое время передачи', required=False)
    cash_pickup_contact = forms.CharField(label='Контакт для передачи', required=False)

    def __init__(self, *args, current_user=None, **kwargs):
        self.current_user = current_user
        super().__init__(*args, **kwargs)
        from apps.dictionaries.models import Region, Specialization
        self.fields['region'].queryset = Region.objects.all()
        self.fields['specializations'].queryset = Specialization.objects.all()
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = (existing + ' form-check-input').strip()
            elif not isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs['class'] = (existing + ' form-control').strip()

    def clean_phone(self):
        digits = ''.join(ch for ch in self.cleaned_data['phone'] if ch.isdigit())
        if digits and digits[0] == '8':
            digits = '7' + digits[1:]
        if len(digits) != 11 or digits[0] != '7':
            raise forms.ValidationError('Введите номер телефона в формате +7 (999) 999-99-99')

        phone = '+7 (' + digits[1:4] + ') ' + digits[4:7] + '-' + digits[7:9] + '-' + digits[9:11]
        if self.current_user and User.objects.filter(phone=phone).exclude(pk=self.current_user.pk).exists():
            raise forms.ValidationError('Этот телефон уже зарегистрирован у другого пользователя')
        return phone


class CollectorNoteForm(forms.Form):
    text = forms.CharField(
        label='Заметка', widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Например: договаривались о сборке по выходным, хорошо работает с техникой'}),
    )
