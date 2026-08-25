import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View

from .models import NotificationLog, PushSubscription

# Соль для подписи deep-link'а — отдельная от остальных сигнатур в проекте,
# чтобы протечка одной не давала подделать другую.
TELEGRAM_LINK_SALT = 'telegram-link'
TELEGRAM_LINK_MAX_AGE = 3600  # ссылка одноразовая по смыслу, но на всякий случай живёт 1 час

# MAX поддерживает диплинки вида https://max.ru/<bot>?start=<payload> (до 128
# символов в payload) — официально подтверждено в dev.max.ru/help/deeplinks.
# Код действует так же 1 час, как и телеграмный.
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
        telegram_link_command = None
        if settings.TELEGRAM_BOT_USERNAME:
            payload = signing.dumps(request.user.pk, salt=TELEGRAM_LINK_SALT)
            deep_link = f'https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={payload}'
            telegram_link_command = f'/start {payload}'

        max_deep_link = None
        max_link_command = None
        if settings.MAX_BOT_USERNAME:
            payload = signing.dumps(request.user.pk, salt=MAX_LINK_SALT)
            max_deep_link = f'https://max.ru/{settings.MAX_BOT_USERNAME}?start={payload}'
            max_link_command = f'/start {payload}'

        recent = NotificationLog.objects.filter(user=request.user).order_by('-created_at')[:20]
        return {
            'deep_link': deep_link,
            'bot_username': settings.TELEGRAM_BOT_USERNAME,
            'telegram_connected': bool(request.user.telegram_chat_id),
            'telegram_link_command': telegram_link_command,
            'max_deep_link': max_deep_link,
            'max_bot_username': settings.MAX_BOT_USERNAME,
            'max_connected': bool(request.user.max_chat_id),
            'max_link_command': max_link_command,
            'vapid_public_key': settings.VAPID_PUBLIC_KEY,
            'push_connected': request.user.push_subscriptions.exists(),
            'recent': recent,
        }


class PushSubscribeView(LoginRequiredMixin, View):
    """Браузер прислал подписку (результат pushManager.subscribe()) — сохраняем
    и включаем push как канал доставки для пользователя."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            endpoint = data['endpoint']
            p256dh = data['keys']['p256dh']
            auth = data['keys']['auth']
        except (json.JSONDecodeError, KeyError):
            return JsonResponse({'ok': False, 'error': 'Некорректные данные подписки'}, status=400)

        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                'user': request.user, 'p256dh': p256dh, 'auth': auth,
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:255],
            },
        )
        request.user.notify_via_push = True
        request.user.save(update_fields=['notify_via_push'])
        return JsonResponse({'ok': True})


class PushUnsubscribeView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            endpoint = json.loads(request.body)['endpoint']
        except (json.JSONDecodeError, KeyError):
            return JsonResponse({'ok': False, 'error': 'Некорректные данные'}, status=400)

        request.user.push_subscriptions.filter(endpoint=endpoint).delete()
        if not request.user.push_subscriptions.exists():
            request.user.notify_via_push = False
            request.user.save(update_fields=['notify_via_push'])
        return JsonResponse({'ok': True})
