from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .views import TELEGRAM_LINK_MAX_AGE, TELEGRAM_LINK_SALT

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
