from django.contrib import admin

from .models import PaymentRecord, Rating


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ('order', 'collector', 'amount', 'is_paid', 'paid_at')
    list_filter = ('is_paid',)
    search_fields = ('collector__username', 'order__id')


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('order', 'collector', 'score', 'deadline_met', 'had_complaint', 'rated_by')
    list_filter = ('score', 'deadline_met', 'had_complaint')
