from django.contrib import admin

from apps.reports.models import PhotoReport

from .models import Order, OrderStatusHistory


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ('from_status', 'to_status', 'changed_by', 'comment', 'created_at')
    can_delete = False


class PhotoReportInline(admin.StackedInline):
    model = PhotoReport
    extra = 0
    readonly_fields = ('status', 'comment', 'manager_comment', 'submitted_at')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'furniture_type', 'status', 'urgency', 'collector', 'deadline_at', 'price')
    list_filter = ('status', 'urgency', 'furniture_type')
    search_fields = ('address', 'client_contact_name')
    inlines = [PhotoReportInline, OrderStatusHistoryInline]
