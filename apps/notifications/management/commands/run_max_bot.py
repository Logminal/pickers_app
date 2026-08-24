"""
Long-polling MAX-бот для привязки аккаунтов (п.6 ТЗ) — второй канал уведомлений
в дополнение к Telegram, пользователь сам выбирает канал(ы) в личном кабинете.

MAX Bot API устроен похоже на Telegram (токен в заголовке Authorization,
получение обновлений через GET /updates), но диплинки с payload (аналог
Telegram ?start=xxx) на момент разработки не подтверждены документацией —
поэтому вместо кликабельной ссылки пользователь копирует команду вида
"/start <подписанный_id>" со страницы «Уведомления» и присылает её боту сам.

Запуск (должен работать постоянно, как отдельный процесс, аналогично
run_telegram_bot):
    python manage.py run_max_bot
На проде — через systemd/supervisor, не через cron (нужен долгоживущий процесс).
"""

import time
from pathlib import Path

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management.base import BaseCommand

from apps.notifications.views import MAX_LINK_MAX_AGE, MAX_LINK_SALT

User = get_user_model()

API_BASE = 'https://platform-api2.max.ru'
MARKER_FILE = Path(settings.BASE_DIR) / '.max_marker'


class Command(BaseCommand):
    help = 'Запускает long-polling MAX-бота для привязки аккаунтов сборщиков/менеджеров.'

    def handle(self, *args, **options):
        if not settings.MAX_BOT_TOKEN:
            self.stderr.write(self.style.ERROR('MAX_BOT_TOKEN не задан в .env — бот не запущен.'))
            return

        marker = self._load_marker()
        self.stdout.write(self.style.SUCCESS('MAX-бот запущен, жду сообщения...'))

        while True:
            try:
                updates, marker = self._get_updates(marker)
            except requests.RequestException as exc:
                self.stderr.write(f'Сеть недоступна ({exc}), повтор через 5 сек.')
                time.sleep(5)
                continue

            for update in updates:
                try:
                    self._handle_update(update)
                except Exception:
                    self.stderr.write(f'Ошибка обработки update {update.get("update_type")}')
            self._save_marker(marker)

    def _get_updates(self, marker):
        # marker=None (первый запуск, нет сохранённого файла) — параметр вообще не
        # передаём: сервер сам вернёт текущую позицию. Передать marker=0 явно — не
        # то же самое, что "с начала": сервер в этом случае молча отдаёт пустой
        # список и marker=0 навсегда, бот застревает (проверено на реальном API).
        params = {'timeout': 30}
        if marker is not None:
            params['marker'] = marker
        resp = requests.get(
            f'{API_BASE}/updates', params=params,
            headers={'Authorization': settings.MAX_BOT_TOKEN}, timeout=40,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get('updates', []), data.get('marker', marker)

    def _handle_update(self, update):
        update_type = update.get('update_type')

        if update_type == 'message_created':
            message = update.get('message', {})
            chat_id = message.get('recipient', {}).get('chat_id')
            chat_type = message.get('recipient', {}).get('chat_type', 'dialog')
            text = (message.get('body', {}) or {}).get('text', '').strip()
            if chat_id is None or not text:
                return
            self._handle_text(chat_id, chat_type, text)
        elif update_type == 'bot_started':
            chat_id = update.get('chat_id')
            if chat_id is not None:
                self._send(
                    chat_id,
                    'Привет! Чтобы подключить уведомления, скопируйте команду со страницы '
                    '«Уведомления» в личном кабинете на сайте и пришлите её сюда сообщением.',
                )

    def _handle_text(self, chat_id, chat_type, text):
        if text.startswith('/start'):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                self._link_account(chat_id, parts[1].strip())
            else:
                self._send(
                    chat_id,
                    'Скопируйте команду целиком со страницы «Уведомления» в личном кабинете — '
                    'она выглядит как "/start <код>".',
                )
        elif text.startswith('/id'):
            # Быстрый способ узнать chat_id — свой или группового чата.
            self._send(chat_id, f'chat_id этого чата ({chat_type}): {chat_id}')
        else:
            self._send(
                chat_id,
                'Этот бот только присылает уведомления от платформы «Сборка мебели». '
                'Команды: /start <код> — подключить уведомления, /id — узнать chat_id этого чата.',
            )

    def _link_account(self, chat_id, payload):
        try:
            user_id = signing.loads(payload, salt=MAX_LINK_SALT, max_age=MAX_LINK_MAX_AGE)
        except signing.SignatureExpired:
            self._send(chat_id, 'Код устарел. Откройте страницу «Уведомления» на сайте ещё раз и скопируйте новый.')
            return
        except signing.BadSignature:
            self._send(chat_id, 'Код недействителен. Откройте страницу «Уведомления» на сайте и попробуйте снова.')
            return

        updated = User.objects.filter(pk=user_id).update(max_chat_id=str(chat_id))
        if updated:
            user = User.objects.get(pk=user_id)
            self._send(chat_id, f'✅ Готово, {user.username}! Теперь уведомления от платформы будут приходить сюда.')
            self.stdout.write(self.style.SUCCESS(f'Привязан MAX для пользователя {user.username} (chat_id={chat_id})'))
        else:
            self._send(chat_id, 'Не удалось найти пользователя. Получите новый код в личном кабинете на сайте.')

    def _send(self, chat_id, text):
        try:
            requests.post(
                f'{API_BASE}/messages', params={'chat_id': chat_id},
                json={'text': text, 'attachments': []},
                headers={'Authorization': settings.MAX_BOT_TOKEN}, timeout=10,
            )
        except requests.RequestException:
            pass

    def _load_marker(self):
        if MARKER_FILE.exists():
            try:
                return int(MARKER_FILE.read_text().strip())
            except ValueError:
                return None
        return None

    def _save_marker(self, marker):
        MARKER_FILE.write_text(str(marker))
