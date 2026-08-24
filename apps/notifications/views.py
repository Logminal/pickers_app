from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View

from .models import NotificationLog

# Соль для подписи deep-link'а — отдельная от остальных сигнатур в проекте,
# чтобы протечка одной не давала подделать другую.
TELEGRAM_LINK_SALT = 'telegram-link'
TELEGRAM_LINK_MAX_AGE = 3600  # ссылка одноразовая по смыслу, но на всякий случай живёт 1 час

# MAX (пока) не подтверждённо поддерживает диплинки с payload (?start=...), поэтому
# вместо кликабельной ссылки показываем пользователю команду для копирования —
# он сам открывает бота в MAX и присылает её текстом. Код действует так же 1 час.
MAX_LINK_SALT = 'max-link'
MAX_LINK_MAX_AGE = 3600


class NotificationSettingsView(LoginRequiredMixin, View):
    """Доступно любой роли — подключение Telegram/MAX, выбор каналов доставки,
    просмотр своих уведомлений."""

    template_name = 'notifications/settings.html'

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        request.user.notify_via_telegram = bool(request.POST.get('notify_via_telegram'))
        request.user.notify_via_max = bool(request.POST.get('notify_via_max'))
        request.user.save(update_fields=['notify_via_telegram', 'notify_via_max'])
        messages.success(request, 'Настройки уведомлений сохранены.')
        return redirect(reverse_lazy('notification_settings'))

    def _context(self, request):
        deep_link = None
        if settings.TELEGRAM_BOT_USERNAME:
            payload = signing.dumps(request.user.pk, salt=TELEGRAM_LINK_SALT)
            deep_link = f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={payload}'

        max_link_command = None
        if settings.MAX_BOT_TOKEN:
            payload = signing.dumps(request.user.pk, salt=MAX_LINK_SALT)
            max_link_command = f'/start {payload}'

        recent = NotificationLog.objects.filter(user=request.user).order_by('-created_at')[:20]
        return {
            'deep_link': deep_link,
            'bot_username': settings.TELEGRAM_BOT_USERNAME,
            'telegram_connected': bool(request.user.telegram_chat_id),
            'max_link_command': max_link_command,
            'max_bot_username': settings.MAX_BOT_USERNAME,
            'max_connected': bool(request.user.max_chat_id),
            'recent': recent,
        }
