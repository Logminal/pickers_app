from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import CollectorProfile, CollectorProfileChangeRequest, PassportData, PaymentDetails


class PassportDataInline(admin.StackedInline):
    """scan_file намеренно исключён из формы — у зашифрованного хранилища нет
    публичного .url(), обычный ClearableFileInput на нём упадёт. Смотреть скан —
    только через защищённую ссылку ниже (с логированием доступа, 152-ФЗ)."""

    model = PassportData
    extra = 0
    fields = (
        'series_number', 'issued_by', 'issue_date', 'division_code',
        'registration_address', 'actual_address', 'scan_link', 'created_at', 'updated_at',
    )
    readonly_fields = ('scan_link', 'created_at', 'updated_at')

    @admin.display(description='Скан паспорта')
    def scan_link(self, obj):
        if not obj.pk or not obj.scan_file:
            return '—'
        url = reverse('passport_scan_view', kwargs={'user_id': obj.collector.user_id})
        return format_html('<a href="{}" target="_blank">🔒 Открыть скан (доступ логируется)</a>', url)


class PaymentDetailsInline(admin.StackedInline):
    model = PaymentDetails
    extra = 0


@admin.register(CollectorProfile)
class CollectorProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'status', 'tax_status', 'region', 'created_at')
    list_filter = ('status', 'tax_status', 'region')
    search_fields = ('full_name', 'user__username', 'user__phone')
    inlines = [PassportDataInline, PaymentDetailsInline]
    actions = ['approve', 'reject']

    @admin.action(description='Подтвердить анкету')
    def approve(self, request, queryset):
        queryset.update(status=CollectorProfile.Status.CONFIRMED)

    @admin.action(description='Отклонить анкету')
    def reject(self, request, queryset):
        queryset.update(status=CollectorProfile.Status.REJECTED)


@admin.register(CollectorProfileChangeRequest)
class CollectorProfileChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('profile', 'status', 'created_at', 'reviewed_by', 'reviewed_at')
    list_filter = ('status',)
    readonly_fields = ('profile', 'changes', 'created_at')
