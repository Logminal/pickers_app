import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.dictionaries.models import Region

from .models import CollectorNote, CollectorProfile, CollectorProfileChangeRequest, PassportData, PaymentDetails
from .services import (
    approve_change_request,
    block_collector,
    delete_collector_permanently,
    reject_change_request,
    set_rating_override,
    submit_profile_change_request,
    unblock_collector,
)

User = get_user_model()


class PassportEncryptionTests(TestCase):
    """152-ФЗ: скан должен быть нечитаем на диске и доступен только роли 'Администратор'."""

    def setUp(self):
        self.collector = User.objects.create_user(username='collector', password='x', role=User.Role.COLLECTOR)
        self.profile = CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
        )
        self.original_content = b'SECRET PASSPORT DATA 12345'
        self.passport = PassportData.objects.create(
            collector=self.profile, series_number='1234 567890', issued_by='ОВД', issue_date='2010-01-01',
            division_code='770-001', registration_address='Москва', actual_address='Москва',
            scan_file=SimpleUploadedFile('scan.txt', self.original_content, content_type='text/plain'),
        )

    def test_file_on_disk_is_not_plaintext(self):
        raw_on_disk = self.passport.scan_file.storage.open(self.passport.scan_file.name, 'rb').read()
        self.assertNotEqual(raw_on_disk, self.original_content)

    def test_decryption_recovers_original_bytes(self):
        decrypted = self.passport.scan_file.storage.open_decrypted(self.passport.scan_file.name)
        self.assertEqual(decrypted, self.original_content)

    def test_manager_cannot_view_passport_scan(self):
        manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        client = Client()
        client.force_login(manager)
        response = client.get(reverse('passport_scan_view', args=[self.collector.pk]))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_view_passport_scan_and_it_gets_logged(self):
        from apps.core.models import PersonalDataAccessLog

        admin = User.objects.create_user(username='admin_user', password='x', role=User.Role.ADMIN)
        client = Client()
        client.force_login(admin)

        response = client.get(reverse('passport_scan_view', args=[self.collector.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.original_content)

        self.assertTrue(
            PersonalDataAccessLog.objects.filter(user=admin, target_collector=self.profile).exists()
        )

    def test_anonymous_cannot_view_passport_scan(self):
        client = Client()
        response = client.get(reverse('passport_scan_view', args=[self.collector.pk]))
        self.assertNotEqual(response.status_code, 200)


class ProfileChangeRequestTests(TestCase):
    """Сборщик меняет свои данные сам, но применяются они только после подтверждения."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(
            username='collector', password='x', role=User.Role.COLLECTOR, phone='+7 (900) 111-11-11',
        )
        self.profile = CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            experience_years=2,
        )
        PaymentDetails.objects.create(collector=self.profile, method='card', card_or_account_number='OLD')

    def _base_form_data(self, **overrides):
        data = {
            'phone': self.collector.phone, 'email': '', 'region': None, 'specializations': [],
            'experience_years': self.profile.experience_years, 'has_own_tools': False, 'tools_list': '',
            'has_car': False, 'willing_to_travel': False, 'emergency_contact': '',
            'payment_method': 'card', 'card_or_account_number': 'OLD', 'sbp_phone': '',
            'cash_pickup_address': '', 'cash_pickup_time': '', 'cash_pickup_contact': '',
        }
        data.update(overrides)
        return data

    def test_no_change_request_created_when_nothing_changed(self):
        result = submit_profile_change_request(self.profile, self._base_form_data())
        self.assertIsNone(result)
        self.assertEqual(CollectorProfileChangeRequest.objects.count(), 0)

    def test_change_request_captures_only_changed_fields(self):
        result = submit_profile_change_request(self.profile, self._base_form_data(experience_years=7))
        self.assertIsNotNone(result)
        self.assertEqual(result.changes, {'profile.experience_years': 7})

    def test_data_unchanged_until_approved(self):
        submit_profile_change_request(self.profile, self._base_form_data(experience_years=7))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.experience_years, 2)

    def test_approve_applies_changes(self):
        region = Region.objects.create(name='Тестовый регион')
        cr = submit_profile_change_request(self.profile, self._base_form_data(
            experience_years=7, region=region, card_or_account_number='NEW_CARD',
        ))
        approve_change_request(cr, self.manager)

        self.profile.refresh_from_db()
        payment = PaymentDetails.objects.get(collector=self.profile)
        cr.refresh_from_db()

        self.assertEqual(self.profile.experience_years, 7)
        self.assertEqual(self.profile.region, region)
        self.assertEqual(payment.card_or_account_number, 'NEW_CARD')
        self.assertEqual(cr.status, CollectorProfileChangeRequest.Status.APPROVED)
        self.assertEqual(cr.reviewed_by, self.manager)

    def test_reject_leaves_data_unchanged(self):
        cr = submit_profile_change_request(self.profile, self._base_form_data(experience_years=99))
        reject_change_request(cr, self.manager, reason='Не похоже на правду')

        self.profile.refresh_from_db()
        cr.refresh_from_db()

        self.assertEqual(self.profile.experience_years, 2)
        self.assertEqual(cr.status, CollectorProfileChangeRequest.Status.REJECTED)
        self.assertEqual(cr.review_comment, 'Не похоже на правду')


class CollectorNoteVisibilityTests(TestCase):
    """Заметки менеджера о сборщике — общие для всех менеджеров/админов,
    недоступны сборщику ни при каких условиях."""

    def setUp(self):
        self.manager1 = User.objects.create_user(username='manager1', password='x', role=User.Role.MANAGER)
        self.manager2 = User.objects.create_user(username='manager2', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector', password='x', role=User.Role.COLLECTOR)
        self.profile = CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )

    def test_manager_can_add_note(self):
        client = Client()
        client.force_login(self.manager1)
        response = client.post(
            reverse('collector_note_add', args=[self.collector.pk]), {'text': 'Хороший мастер'},
        )
        self.assertEqual(response.status_code, 302)
        note = CollectorNote.objects.get(profile=self.profile)
        self.assertEqual(note.text, 'Хороший мастер')
        self.assertEqual(note.author, self.manager1)

    def test_note_visible_to_other_managers(self):
        CollectorNote.objects.create(profile=self.profile, author=self.manager1, text='Заметка от первого менеджера')

        client = Client()
        client.force_login(self.manager2)
        response = client.get(reverse('collector_profile_detail', args=[self.collector.pk]))

        self.assertContains(response, 'Заметка от первого менеджера')

    def test_collector_cannot_access_own_profile_notes_page(self):
        client = Client()
        client.force_login(self.collector)
        response = client.get(reverse('collector_profile_detail', args=[self.collector.pk]))
        self.assertEqual(response.status_code, 403)

    def test_collector_cannot_add_note(self):
        client = Client()
        client.force_login(self.collector)
        response = client.post(
            reverse('collector_note_add', args=[self.collector.pk]), {'text': 'Попытка добавить заметку'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CollectorNote.objects.exists())

    def test_empty_note_rejected(self):
        client = Client()
        client.force_login(self.manager1)
        client.post(reverse('collector_note_add', args=[self.collector.pk]), {'text': ''})
        self.assertFalse(CollectorNote.objects.exists())


class ReviewsDisplayTests(TestCase):
    """Отзывы (оценки с комментарием) должны быть видны отдельно от голых оценок."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector', password='x', role=User.Role.COLLECTOR)
        self.profile = CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )

    def test_only_ratings_with_comment_shown_as_reviews(self):
        from apps.dictionaries.models import FurnitureType
        from apps.orders.models import Order
        from apps.payments.models import Rating

        from django.utils import timezone

        now = timezone.now()
        ft = FurnitureType.objects.create(name='Кухня')
        order_with_comment = Order.objects.create(
            furniture_type=ft, address='ул. А, 1', scheduled_at=now, deadline_at=now, price=1000,
            status=Order.Status.CLOSED, created_by=self.manager, collector=self.collector,
        )
        order_without_comment = Order.objects.create(
            furniture_type=ft, address='ул. Б, 1', scheduled_at=now, deadline_at=now, price=1000,
            status=Order.Status.CLOSED, created_by=self.manager, collector=self.collector,
        )
        Rating.objects.create(order=order_with_comment, collector=self.collector, rated_by=self.manager, score=5, comment='Отличная работа')
        Rating.objects.create(order=order_without_comment, collector=self.collector, rated_by=self.manager, score=4, comment='')

        client = Client()
        client.force_login(self.manager)
        response = client.get(reverse('collector_profile_detail', args=[self.collector.pk]))

        self.assertEqual(len(response.context['reviews']), 1)
        self.assertEqual(len(response.context['ratings']), 2)
        self.assertContains(response, 'Отличная работа')


class BlockingAndRatingOverrideModelTests(TestCase):
    """CollectorProfile.is_blocked/average_rating — правила, от которых зависит book_order."""

    def setUp(self):
        self.collector = User.objects.create_user(username='collector', password='x', role=User.Role.COLLECTOR)
        self.profile = CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )

    def test_not_blocked_by_default(self):
        self.assertFalse(self.profile.is_blocked)

    def test_permanent_block_via_status(self):
        self.profile.status = CollectorProfile.Status.BLOCKED
        self.profile.save()
        self.assertTrue(self.profile.is_blocked)

    def test_future_blocked_until_is_blocked(self):
        self.profile.blocked_until = timezone.now() + datetime.timedelta(days=1)
        self.profile.save()
        self.assertTrue(self.profile.is_blocked)

    def test_past_blocked_until_is_not_blocked(self):
        self.profile.blocked_until = timezone.now() - datetime.timedelta(days=1)
        self.profile.save()
        self.assertFalse(self.profile.is_blocked)

    def test_rating_override_takes_priority_over_computed_average(self):
        from apps.dictionaries.models import FurnitureType
        from apps.orders.models import Order
        from apps.payments.models import Rating

        manager = User.objects.create_user(username='manager_ro', password='x', role=User.Role.MANAGER)
        ft = FurnitureType.objects.create(name='Кухня')
        order = Order.objects.create(
            furniture_type=ft, address='ул. А, 1', scheduled_at=timezone.now(), deadline_at=timezone.now(),
            price=1000, status=Order.Status.CLOSED, created_by=manager, collector=self.collector,
        )
        Rating.objects.create(order=order, collector=self.collector, rated_by=manager, score=3, comment='')
        self.assertEqual(self.profile.average_rating, 3)

        self.profile.rating_override = Decimal('4.5')
        self.profile.save()
        self.assertEqual(self.profile.average_rating, Decimal('4.5'))

    def test_average_rating_none_without_ratings_or_override(self):
        self.assertIsNone(self.profile.average_rating)


class BlockingServiceTests(TestCase):
    def setUp(self):
        self.collector = User.objects.create_user(username='collector', password='x', role=User.Role.COLLECTOR)
        self.profile = CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )

    def test_block_collector_permanently(self):
        block_collector(self.profile, reason='Пропал')
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, CollectorProfile.Status.BLOCKED)
        self.assertIsNone(self.profile.blocked_until)
        self.assertEqual(self.profile.block_reason, 'Пропал')

    def test_block_collector_temporarily_keeps_status_confirmed(self):
        until = timezone.now() + datetime.timedelta(days=3)
        block_collector(self.profile, reason='Жалоба клиента', until=until)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, CollectorProfile.Status.CONFIRMED)
        self.assertEqual(self.profile.blocked_until, until)
        self.assertTrue(self.profile.is_blocked)

    def test_unblock_after_permanent_block_restores_confirmed(self):
        block_collector(self.profile)
        unblock_collector(self.profile)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, CollectorProfile.Status.CONFIRMED)
        self.assertFalse(self.profile.is_blocked)

    def test_unblock_clears_temporary_block(self):
        block_collector(self.profile, until=timezone.now() + datetime.timedelta(days=1))
        unblock_collector(self.profile)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.blocked_until)
        self.assertFalse(self.profile.is_blocked)

    def test_set_rating_override(self):
        set_rating_override(self.profile, Decimal('2.5'))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.rating_override, Decimal('2.5'))

    def test_clear_rating_override(self):
        set_rating_override(self.profile, Decimal('2.5'))
        set_rating_override(self.profile, None)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.rating_override)

    def test_delete_collector_permanently_removes_user_and_profile(self):
        user_id = self.collector.pk
        delete_collector_permanently(self.profile)
        self.assertFalse(User.objects.filter(pk=user_id).exists())
        self.assertFalse(CollectorProfile.objects.filter(pk=self.profile.pk).exists())

    def test_delete_collector_preserves_order_history_via_null(self):
        from apps.dictionaries.models import FurnitureType
        from apps.orders.models import Order

        manager = User.objects.create_user(username='manager_del', password='x', role=User.Role.MANAGER)
        ft = FurnitureType.objects.create(name='Кухня')
        order = Order.objects.create(
            furniture_type=ft, address='ул. А, 1', scheduled_at=timezone.now(), deadline_at=timezone.now(),
            price=1000, status=Order.Status.CLOSED, created_by=manager, collector=self.collector,
        )
        delete_collector_permanently(self.profile)
        order.refresh_from_db()
        self.assertIsNone(order.collector)


class AdminBlockingViewsTests(TestCase):
    """Управление аккаунтом сборщика доступно только роли 'Администратор' (не менеджеру)."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin_block', password='x', role=User.Role.ADMIN)
        self.manager = User.objects.create_user(username='manager_block', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector_block', password='x', role=User.Role.COLLECTOR)
        self.profile = CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )

    def test_manager_cannot_block(self):
        client = Client()
        client.force_login(self.manager)
        response = client.post(reverse('collector_block', args=[self.collector.pk]), {'reason': 'Тест'})
        self.assertEqual(response.status_code, 403)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_blocked)

    def test_admin_permanent_block(self):
        client = Client()
        client.force_login(self.admin)
        response = client.post(reverse('collector_block', args=[self.collector.pk]), {'reason': 'Пропал'})
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, CollectorProfile.Status.BLOCKED)

    def test_admin_temporary_block_with_valid_future_date(self):
        until = timezone.now() + datetime.timedelta(days=2)
        client = Client()
        client.force_login(self.admin)
        response = client.post(reverse('collector_block', args=[self.collector.pk]), {
            'reason': 'Жалоба', 'blocked_until': until.isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_blocked)
        self.assertEqual(self.profile.status, CollectorProfile.Status.CONFIRMED)

    def test_admin_block_rejects_past_date(self):
        past = timezone.now() - datetime.timedelta(days=1)
        client = Client()
        client.force_login(self.admin)
        client.post(reverse('collector_block', args=[self.collector.pk]), {
            'reason': 'Жалоба', 'blocked_until': past.isoformat(),
        })
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_blocked)

    def test_admin_block_rejects_garbage_date(self):
        client = Client()
        client.force_login(self.admin)
        client.post(reverse('collector_block', args=[self.collector.pk]), {
            'reason': 'Жалоба', 'blocked_until': 'not-a-date',
        })
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_blocked)

    def test_admin_unblock(self):
        block_collector(self.profile)
        client = Client()
        client.force_login(self.admin)
        response = client.post(reverse('collector_unblock', args=[self.collector.pk]))
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_blocked)

    def test_admin_sets_rating_override(self):
        client = Client()
        client.force_login(self.admin)
        response = client.post(
            reverse('collector_rating_override', args=[self.collector.pk]), {'rating_override': '3.5'},
        )
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.rating_override, Decimal('3.5'))

    def test_admin_clears_rating_override_with_empty_value(self):
        set_rating_override(self.profile, Decimal('4'))
        client = Client()
        client.force_login(self.admin)
        client.post(reverse('collector_rating_override', args=[self.collector.pk]), {'rating_override': ''})
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.rating_override)

    def test_admin_rating_override_rejects_out_of_range(self):
        client = Client()
        client.force_login(self.admin)
        client.post(reverse('collector_rating_override', args=[self.collector.pk]), {'rating_override': '9'})
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.rating_override)

    def test_admin_rating_override_rejects_non_numeric(self):
        client = Client()
        client.force_login(self.admin)
        client.post(reverse('collector_rating_override', args=[self.collector.pk]), {'rating_override': 'abc'})
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.rating_override)

    def test_manager_cannot_delete_collector(self):
        client = Client()
        client.force_login(self.manager)
        response = client.post(reverse('collector_delete', args=[self.collector.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.collector.pk).exists())

    def test_admin_deletes_collector(self):
        client = Client()
        client.force_login(self.admin)
        response = client.post(reverse('collector_delete', args=[self.collector.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.collector.pk).exists())
