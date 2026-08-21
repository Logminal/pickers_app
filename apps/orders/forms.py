from django import forms

from .models import Order


class OrderCreateForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            'furniture_type', 'required_specialization', 'address',
            'scheduled_at', 'deadline_at', 'urgency', 'spec_file',
            'dimensions', 'modules_count', 'bitrix_deal_id', 'price',
            'bitrix_item_amount', 'bitrix_assembly_percent', 'bitrix_installation_amount',
            'bitrix_additional_services_amount', 'bitrix_lift_amount', 'bitrix_delivery_amount',
            'comment', 'client_contact_name', 'client_contact_phone',
        ]
        labels = {
            'bitrix_deal_id': 'Номер сделки в Bitrix24 (необязательно)',
            'bitrix_item_amount': 'Сумма изделия',
            'bitrix_assembly_percent': 'Процент сборки (цеха), %',
            'bitrix_installation_amount': 'Монтаж',
            'bitrix_additional_services_amount': 'Доп. услуги',
            'bitrix_lift_amount': 'Подъём',
            'bitrix_delivery_amount': 'Доставка',
        }
        widgets = {
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'deadline_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'comment': forms.Textarea(attrs={'rows': 3}),
            'price': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01', 'inputmode': 'decimal', 'id': 'id_price'}),
            'modules_count': forms.NumberInput(attrs={'min': '0', 'step': '1', 'inputmode': 'numeric'}),
            'bitrix_deal_id': forms.TextInput(attrs={'id': 'id_bitrix_deal_id', 'inputmode': 'numeric'}),
            'bitrix_item_amount': forms.NumberInput(attrs={'id': 'id_bitrix_item_amount', 'step': '0.01', 'readonly': True}),
            'bitrix_assembly_percent': forms.NumberInput(attrs={'id': 'id_bitrix_assembly_percent', 'step': '0.01', 'readonly': True}),
            'bitrix_installation_amount': forms.NumberInput(attrs={'id': 'id_bitrix_installation_amount', 'step': '0.01', 'readonly': True}),
            'bitrix_additional_services_amount': forms.NumberInput(attrs={'id': 'id_bitrix_additional_services_amount', 'step': '0.01', 'readonly': True}),
            'bitrix_lift_amount': forms.NumberInput(attrs={'id': 'id_bitrix_lift_amount', 'step': '0.01', 'readonly': True}),
            'bitrix_delivery_amount': forms.NumberInput(attrs={'id': 'id_bitrix_delivery_amount', 'step': '0.01', 'readonly': True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (existing + ' form-control').strip()

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise forms.ValidationError('Стоимость должна быть положительным числом.')
        return price
