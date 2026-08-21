from django.contrib import admin

from .models import PersonalDataAccessLog

admin.site.site_header = 'Платформа сборщиков мебели'
admin.site.site_title = 'Администрирование'
admin.site.index_title = 'Панель управления'


@admin.register(PersonalDataAccessLog)
class PersonalDataAccessLogAdmin(admin.ModelAdmin):
    """Журнал доступа к персональным данным (152-ФЗ, п.2.3 / п.7 ТЗ) — только просмотр."""

    list_display = ('created_at', 'user', 'target_collector', 'action', 'ip_address')
    list_filter = ('action',)
    search_fields = ('user__username', 'target_collector__full_name', 'ip_address')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
