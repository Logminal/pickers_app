from django.contrib import admin

from .models import PaymentRecord, Rating, WithdrawalRequest


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('order', 'collector', 'amount', 'is_paid', 'paid_at')
    list_filter = ('is_paid',)
    search_fields = ('collector__username', 'order__id')


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('order', 'collector', 'score', 'deadline_met', 'had_complaint', 'rated_by')
    list_filter = ('score', 'deadline_met', 'had_complaint')


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('collector', 'amount', 'method', 'status', 'created_at', 'handled_by')
    list_filter = ('status', 'method')
    search_fields = ('collector__username', 'requisite')
    readonly_fields = ('payment_records',)
