from django.contrib import admin

from .models import NotificationLog, PushSubscription


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    """Пока реальная доставка (Telegram-бот) не подключена, это единственное
    место, где видно, какие уведомления система пыталась отправить и кому."""

    list_display = ('created_at', 'user', 'event_type', 'channel', 'status')
    list_filter = ('status', 'channel', 'event_type')
    search_fields = ('user__username', 'message')
    date_hierarchy = 'created_at'
    readonly_fields = ('user', 'channel', 'event_type', 'message', 'status', 'created_at', 'sent_at')

    def has_add_permission(self, request):
        return False


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'user_agent', 'created_at')
    search_fields = ('user__username', 'endpoint')
    readonly_fields = ('user', 'endpoint', 'p256dh', 'auth', 'user_agent', 'created_at')

    def has_add_permission(self, request):
        return False
