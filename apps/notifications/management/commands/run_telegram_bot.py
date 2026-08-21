"""
Long-polling Telegram-бот для привязки аккаунтов (п.6 ТЗ).

Сервер локальный/без публичного HTTPS, поэтому webhook не годится —
используем getUpdates в цикле. Единственная задача бота: принять команду
/start <подписанный_id_пользователя>, которую пользователь получает по
ссылке из личного кабинета (раздел «Уведомления»), и записать chat_id
в User.telegram_chat_id — после этого notify() начинает реально доставлять
сообщения.

Запуск (должен работать постоянно, как отдельный процесс):
    python manage.py run_telegram_bot
На проде — через systemd/supervisor, не через cron (нужен долгоживущий процесс).
"""

import time
from pathlib import Path

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management.base import BaseCommand

from apps.notifications.views import TELEGRAM_LINK_MAX_AGE, TELEGRAM_LINK_SALT

User = get_user_model()

API_BASE = 'https://api.telegram.org/bot{token}/{method}'
OFFSET_FILE = Path(settings.BASE_DIR) / '.telegram_offset'


class Command(BaseCommand):
    help = 'Запускает long-polling Telegram-бота для привязки аккаунтов сборщиков/менеджеров.'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            self.stderr.write(self.style.ERROR('TELEGRAM_BOT_TOKEN не задан в .env — бот не запущен.'))
            return

        offset = self._load_offset()
        self.stdout.write(self.style.SUCCESS(f'Бот запущен (@{settings.TELEGRAM_BOT_USERNAME}), жду сообщения...'))

        while True:
            try:
                updates = self._get_updates(offset)
            except requests.RequestException as exc:
                self.stderr.write(f'Сеть недоступна ({exc}), повтор через 5 сек.')
                time.sleep(5)
                continue

            for update in updates:
                offset = update['update_id'] + 1
                try:
                    self._handle_update(update)
                except Exception:
                    self.stderr.write(f'Ошибка обработки update {update.get("update_id")}')
                self._save_offset(offset)

    def _get_updates(self, offset):
        url = API_BASE.format(token=settings.TELEGRAM_BOT_TOKEN, method='getUpdates')
        resp = requests.get(url, params={'offset': offset, 'timeout': 30}, timeout=40)
        resp.raise_for_status()
        return resp.json().get('result', [])

    def _handle_update(self, update):
        message = update.get('message')
        if not message or 'text' not in message:
            return

        chat_id = message['chat']['id']
        chat_type = message['chat'].get('type', 'private')
        text = message['text'].strip()

        if text.startswith('/start'):
            parts = text.split(maxsplit=1)
            if len(parts) == 2:
                self._link_account(chat_id, parts[1].strip())
            else:
                self._send(
                    chat_id,
                    'Привет! Чтобы подключить уведомления, откройте ссылку в личном кабинете на сайте '
                    '(раздел «Уведомления») — она приведёт сюда с готовой командой.',
                )
        elif text.startswith('/id'):
            # Быстрый способ узнать chat_id — свой или группового чата (например, чтобы
            # завести общий чат менеджеров и указать его id вручную через Django Admin).
            self._send(chat_id, f'chat_id этого чата ({chat_type}): {chat_id}')
        else:
            self._send(
                chat_id,
                'Этот бот только присылает уведомления от платформы «Сборка мебели». '
                'Команды: /start — подключить уведомления, /id — узнать chat_id этого чата.',
            )

    def _link_account(self, chat_id, payload):
        try:
            user_id = signing.loads(payload, salt=TELEGRAM_LINK_SALT, max_age=TELEGRAM_LINK_MAX_AGE)
        except signing.SignatureExpired:
            self._send(chat_id, 'Ссылка устарела. Откройте страницу «Уведомления» на сайте ещё раз и получите новую.')
            return
        except signing.BadSignature:
            self._send(chat_id, 'Ссылка недействительна. Откройте страницу «Уведомления» на сайте и попробуйте снова.')
            return

        updated = User.objects.filter(pk=user_id).update(telegram_chat_id=str(chat_id))
        if updated:
            user = User.objects.get(pk=user_id)
            self._send(chat_id, f'✅ Готово, {user.username}! Теперь уведомления от платформы будут приходить сюда.')
            self.stdout.write(self.style.SUCCESS(f'Привязан Telegram для пользователя {user.username} (chat_id={chat_id})'))
        else:
            self._send(chat_id, 'Не удалось найти пользователя. Получите новую ссылку в личном кабинете на сайте.')

    def _send(self, chat_id, text):
        url = API_BASE.format(token=settings.TELEGRAM_BOT_TOKEN, method='sendMessage')
        try:
            requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=10)
        except requests.RequestException:
            pass

    def _load_offset(self):
        if OFFSET_FILE.exists():
            try:
                return int(OFFSET_FILE.read_text().strip())
            except ValueError:
                return 0
        return 0

    def _save_offset(self, offset):
        OFFSET_FILE.write_text(str(offset))
