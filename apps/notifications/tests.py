from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import NotificationLog
from .services import notify, notify_staff
from .views import MAX_LINK_MAX_AGE, MAX_LINK_SALT, TELEGRAM_LINK_MAX_AGE, TELEGRAM_LINK_SALT

User = get_user_model()


@override_settings(TELEGRAM_BOT_USERNAME='test_bot')
class NotificationSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='x', role=User.Role.COLLECTOR)

    def test_deep_link_generated_when_bot_configured(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))

        self.assertIsNotNone(response.context['deep_link'])
        self.assertIn('https://t.me/test_bot?start=', response.context['deep_link'])

    def test_deep_link_payload_resolves_back_to_user(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))

        payload = response.context['deep_link'].split('?start=')[1]
        resolved_user_id = signing.loads(payload, salt=TELEGRAM_LINK_SALT, max_age=TELEGRAM_LINK_MAX_AGE)
        self.assertEqual(resolved_user_id, self.user.pk)

    def test_shows_not_connected_when_no_chat_id(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))
        self.assertFalse(response.context['telegram_connected'])

    def test_shows_connected_when_chat_id_set(self):
        self.user.telegram_chat_id = '123456'
        self.user.save()

        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))
        self.assertTrue(response.context['telegram_connected'])

    @override_settings(TELEGRAM_BOT_USERNAME='')
    def test_no_deep_link_when_bot_not_configured(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))
        self.assertIsNone(response.context['deep_link'])

    def test_requires_login(self):
        client = Client()
        response = client.get(reverse('notification_settings'))
        self.assertEqual(response.status_code, 302)


class TelegramLinkSigningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u2', password='x', role=User.Role.MANAGER)

    def test_expired_link_rejected(self):
        payload = signing.dumps(self.user.pk, salt=TELEGRAM_LINK_SALT)
        with self.assertRaises(signing.SignatureExpired):
            signing.loads(payload, salt=TELEGRAM_LINK_SALT, max_age=-1)

    def test_tampered_salt_rejected(self):
        payload = signing.dumps(self.user.pk, salt=TELEGRAM_LINK_SALT)
        with self.assertRaises(signing.BadSignature):
            signing.loads(payload, salt='wrong-salt', max_age=TELEGRAM_LINK_MAX_AGE)

    def test_valid_payload_resolves_to_correct_user(self):
        payload = signing.dumps(self.user.pk, salt=TELEGRAM_LINK_SALT)
        resolved = signing.loads(payload, salt=TELEGRAM_LINK_SALT, max_age=TELEGRAM_LINK_MAX_AGE)
        self.assertEqual(resolved, self.user.pk)


@override_settings(TELEGRAM_BOT_TOKEN='fake-token-for-tests')
class StaffGroupNotificationTests(TestCase):
    """Уведомления менеджерам/админам — в общий чат, без дублирования по числу менеджеров."""

    def setUp(self):
        self.managers = [
            User.objects.create_user(username=f'm{i}', password='x', role=User.Role.MANAGER)
            for i in range(3)
        ]
        self.admin = User.objects.create_user(username='a1', password='x', role=User.Role.ADMIN)
        self.collector = User.objects.create_user(username='c1', password='x', role=User.Role.COLLECTOR)

    @override_settings(TELEGRAM_STAFF_GROUP_CHAT_ID='-100200300')
    @patch('apps.notifications.services.requests.post')
    def test_notify_staff_sends_single_message_to_group(self, mock_post):
        mock_post.return_value.raise_for_status = lambda: None

        logs = notify_staff('some_event', 'Текст')

        self.assertEqual(len(logs), 1)
        self.assertIsNone(logs[0].user)
        self.assertEqual(mock_post.call_count, 1)
        sent_chat_id = mock_post.call_args.kwargs['json']['chat_id']
        self.assertEqual(sent_chat_id, '-100200300')

    @override_settings(TELEGRAM_STAFF_GROUP_CHAT_ID='')
    @patch('apps.notifications.services.requests.post')
    def test_notify_staff_falls_back_to_individual_when_no_group_configured(self, mock_post):
        mock_post.return_value.raise_for_status = lambda: None

        logs = notify_staff('some_event', 'Текст')

        # 3 менеджера + 1 админ = 4 индивидуальных лога
        self.assertEqual(len(logs), 4)
        self.assertTrue(all(log.user is not None for log in logs))

    @override_settings(TELEGRAM_STAFF_GROUP_CHAT_ID='-100200300')
    @patch('apps.notifications.services.requests.post')
    def test_individual_notify_to_manager_redirects_to_group(self, mock_post):
        """notify(manager, ...) в обычных местах кода (book_order и т.п.) должен
        автоматически уйти в общий чат, если он настроен — без правок вызывающего кода."""
        mock_post.return_value.raise_for_status = lambda: None

        logs = notify(self.managers[0], 'order_booked', 'Текст')

        sent_chat_id = mock_post.call_args.kwargs['json']['chat_id']
        self.assertEqual(sent_chat_id, '-100200300')
        self.assertEqual(logs[0].user, self.managers[0])  # лог всё ещё привязан к менеджеру

    @override_settings(TELEGRAM_STAFF_GROUP_CHAT_ID='-100200300')
    @patch('apps.notifications.services.requests.post')
    def test_collector_notification_not_redirected_to_staff_group(self, mock_post):
        self.collector.telegram_chat_id = '555'
        self.collector.save()
        mock_post.return_value.raise_for_status = lambda: None

        notify(self.collector, 'report_accepted', 'Текст')

        sent_chat_id = mock_post.call_args.kwargs['json']['chat_id']
        self.assertEqual(sent_chat_id, '555')

    @override_settings(TELEGRAM_STAFF_GROUP_CHAT_ID='-100200300')
    def test_collector_without_chat_id_fails_not_redirected(self):
        logs = notify(self.collector, 'report_accepted', 'Текст')
        self.assertEqual(logs[0].status, NotificationLog.Status.FAILED)


@override_settings(MAX_BOT_USERNAME='test_max_bot', MAX_BOT_TOKEN='fake-max-token')
class MaxLinkSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='u3', password='x', role=User.Role.COLLECTOR)

    def test_deep_link_generated_when_bot_configured(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))

        self.assertIsNotNone(response.context['max_deep_link'])
        self.assertIn('https://max.ru/test_max_bot?start=', response.context['max_deep_link'])

    def test_deep_link_payload_resolves_back_to_user(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))

        payload = response.context['max_deep_link'].split('?start=')[1]
        resolved_user_id = signing.loads(payload, salt=MAX_LINK_SALT, max_age=MAX_LINK_MAX_AGE)
        self.assertEqual(resolved_user_id, self.user.pk)

    @override_settings(MAX_BOT_USERNAME='')
    def test_no_deep_link_when_bot_not_configured(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))
        self.assertIsNone(response.context['max_deep_link'])

    def test_shows_not_connected_when_no_max_chat_id(self):
        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))
        self.assertFalse(response.context['max_connected'])

    def test_shows_connected_when_max_chat_id_set(self):
        self.user.max_chat_id = '654321'
        self.user.save()

        client = Client()
        client.force_login(self.user)
        response = client.get(reverse('notification_settings'))
        self.assertTrue(response.context['max_connected'])


class ChannelPreferenceTests(TestCase):
    """Пользователь сам выбирает канал(ы) доставки уведомлений."""

    def setUp(self):
        self.user = User.objects.create_user(username='u4', password='x', role=User.Role.COLLECTOR)

    def test_saving_preferences_updates_user(self):
        client = Client()
        client.force_login(self.user)

        client.post(reverse('notification_settings'), {'notify_via_telegram': '', 'notify_via_max': 'on'})

        self.user.refresh_from_db()
        self.assertFalse(self.user.notify_via_telegram)
        self.assertTrue(self.user.notify_via_max)

    @patch('apps.notifications.services.requests.post')
    def test_notify_sends_to_both_channels_when_both_enabled(self, mock_post):
        mock_post.return_value.raise_for_status = lambda: None
        self.user.telegram_chat_id = '111'
        self.user.max_chat_id = '222'
        self.user.notify_via_telegram = True
        self.user.notify_via_max = True
        self.user.save()

        logs = notify(self.user, 'some_event', 'Текст')

        self.assertEqual(len(logs), 2)
        self.assertEqual({log.channel for log in logs}, {NotificationLog.Channel.TELEGRAM, NotificationLog.Channel.MAX})
        self.assertTrue(all(log.status == NotificationLog.Status.SENT for log in logs))
        self.assertEqual(mock_post.call_count, 2)

    @patch('apps.notifications.services.requests.post')
    def test_notify_sends_only_to_max_when_telegram_disabled(self, mock_post):
        mock_post.return_value.raise_for_status = lambda: None
        self.user.max_chat_id = '222'
        self.user.notify_via_telegram = False
        self.user.notify_via_max = True
        self.user.save()

        logs = notify(self.user, 'some_event', 'Текст')

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].channel, NotificationLog.Channel.MAX)

    def test_notify_falls_back_to_telegram_when_no_channel_enabled(self):
        """Защита от 'молчания' — если пользователь случайно снял все галочки."""
        self.user.notify_via_telegram = False
        self.user.notify_via_max = False
        self.user.save()

        logs = notify(self.user, 'some_event', 'Текст')

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].channel, NotificationLog.Channel.TELEGRAM)

    @patch('apps.notifications.services.requests.post')
    def test_max_message_uses_authorization_header_and_chat_id_query_param(self, mock_post):
        mock_post.return_value.raise_for_status = lambda: None
        self.user.max_chat_id = '222'
        self.user.notify_via_max = True
        self.user.save()

        with override_settings(MAX_BOT_TOKEN='fake-max-token'):
            notify(self.user, 'some_event', 'Текст', channels=[NotificationLog.Channel.MAX])

        call = mock_post.call_args
        self.assertEqual(call.kwargs['params']['chat_id'], '222')
        self.assertEqual(call.kwargs['headers']['Authorization'], 'fake-max-token')
        self.assertEqual(call.kwargs['json']['text'], 'Текст')

    def test_max_without_chat_id_fails(self):
        logs = notify(self.user, 'some_event', 'Текст', channels=[NotificationLog.Channel.MAX])
        self.assertEqual(logs[0].status, NotificationLog.Status.FAILED)
