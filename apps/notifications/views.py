from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.shortcuts import render
from django.views import View

from .models import NotificationLog

# Соль для подписи deep-link'а — отдельная от остальных сигнатур в проекте,
# чтобы протечка одной не давала подделать другую.
TELEGRAM_LINK_SALT = 'telegram-link'
TELEGRAM_LINK_MAX_AGE = 3600  # ссылка одноразовая по смыслу, но на всякий случай живёт 1 час


class NotificationSettingsView(LoginRequiredMixin, View):
    """Доступно любой роли — подключение Telegram и просмотр своих уведомлений."""

    template_name = 'notifications/settings.html'

    def get(self, request):
        deep_link = None
        if settings.TELEGRAM_BOT_USERNAME:
            payload = signing.dumps(request.user.pk, salt=TELEGRAM_LINK_SALT)
            deep_link = f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={payload}'

        recent = NotificationLog.objects.filter(user=request.user).order_by('-created_at')[:20]
        return render(request, self.template_name, {
            'deep_link': deep_link,
            'bot_username': settings.TELEGRAM_BOT_USERNAME,
            'telegram_connected': bool(request.user.telegram_chat_id),
            'recent': recent,
        })
