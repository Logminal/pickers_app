import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.collectors.models import CollectorProfile
from apps.dictionaries.models import FurnitureType
from apps.orders.models import Order
from apps.orders.services import book_order, confirm_booking

from .models import Act, AdditionalWork, PhotoSlotDefinition, PhotoSlotTemplate
from .services import close_order, review_photo_report, submit_photo_report

User = get_user_model()


class PhotoReportAndActTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector', password='x', role=User.Role.COLLECTOR)
        CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )

        self.template = PhotoSlotTemplate.objects.create(name='Кухня — тест')
        self.required_slot = PhotoSlotDefinition.objects.create(
            template=self.template, title='Общий вид', is_required=True, order=0,
        )
        self.optional_slot = PhotoSlotDefinition.objects.create(
            template=self.template, title='Инструмент', is_required=False, order=1,
        )
        self.ft = FurnitureType.objects.create(name='Кухня', photo_slots_template=self.template)

        self.order = Order.objects.create(
            furniture_type=self.ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('10000'),
            status=Order.Status.PUBLISHED, created_by=self.manager,
        )
        book_order(self.order.pk, self.collector)
        confirm_booking(self.order.pk, self.manager)
        self.order.refresh_from_db()

    def _submit_report(self, additional_works=None):
        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        report = submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.required_slot.id: photo}, checked_items=[], comment='Готово',
            additional_works=additional_works,
        )
        self.order.refresh_from_db()
        return report

    def test_submit_photo_report_moves_order_to_report_uploaded(self):
        self._submit_report()
        self.assertEqual(self.order.status, Order.Status.REPORT_UPLOADED)

    def test_additional_works_included_in_total_price(self):
        self._submit_report(additional_works=[{'description': 'Демонтаж техники', 'price': Decimal('1500')}])
        self.assertEqual(self.order.additional_works_total, Decimal('1500'))
        self.assertEqual(self.order.total_price, Decimal('11500'))

    def test_cannot_close_order_without_act(self):
        self._submit_report()
        review_photo_report(
            self.order, self.manager, accepted=True,
            manager_act_file=SimpleUploadedFile('manager_act.pdf', b'manager-act-bytes', content_type='application/pdf'),
        )
        self.order.refresh_from_db()

        with self.assertRaises(ValueError):
            close_order(self.order, self.manager)

    def test_cannot_close_order_with_unconfirmed_act_readability(self):
        self._submit_report()
        review_photo_report(
            self.order, self.manager, accepted=True,
            manager_act_file=SimpleUploadedFile('manager_act.pdf', b'manager-act-bytes', content_type='application/pdf'),
        )
        self.order.refresh_from_db()

        Act.objects.update_or_create(
            order=self.order, defaults={
                'file': SimpleUploadedFile('act.pdf', b'x', content_type='application/pdf'),
                'uploaded_by': self.manager, 'is_readable_confirmed': False,
            },
        )

        with self.assertRaises(ValueError):
            close_order(self.order, self.manager)

    def test_close_order_succeeds_with_confirmed_readable_act(self):
        self._submit_report()
        review_photo_report(
            self.order, self.manager, accepted=True,
            manager_act_file=SimpleUploadedFile('manager_act.pdf', b'manager-act-bytes', content_type='application/pdf'),
        )
        self.order.refresh_from_db()

        Act.objects.update_or_create(
            order=self.order, defaults={
                'file': SimpleUploadedFile('act.pdf', b'x', content_type='application/pdf'),
                'uploaded_by': self.manager, 'is_readable_confirmed': True,
            },
        )

        close_order(self.order, self.manager)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CLOSED)
        self.assertIsNotNone(self.order.closed_at)

    def test_reject_photo_report_sends_back_for_rework(self):
        self._submit_report()
        review_photo_report(self.order, self.manager, accepted=False, comment='Плохие фото')
        self.order.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.REJECTED_FOR_REWORK)
        self.assertEqual(self.order.photo_report.status, self.order.photo_report.Status.REJECTED)

    def test_close_order_creates_payment_record(self):
        from apps.payments.models import PaymentRecord

        self._submit_report(additional_works=[{'description': 'Доп. работа', 'price': Decimal('500')}])
        review_photo_report(
            self.order, self.manager, accepted=True,
            manager_act_file=SimpleUploadedFile('manager_act.pdf', b'manager-act-bytes', content_type='application/pdf'),
        )
        self.order.refresh_from_db()
        Act.objects.update_or_create(
            order=self.order, defaults={
                'file': SimpleUploadedFile('act.pdf', b'x', content_type='application/pdf'),
                'uploaded_by': self.manager, 'is_readable_confirmed': True,
            },
        )
        close_order(self.order, self.manager)

        record = PaymentRecord.objects.get(order=self.order)
        self.assertEqual(record.amount, Decimal('10500'))
        self.assertFalse(record.is_paid)

    def test_payment_record_syncs_when_additional_work_added_after_closure(self):
        from apps.payments.models import PaymentRecord
        from apps.payments.services import mark_payment_paid

        self._submit_report()
        review_photo_report(
            self.order, self.manager, accepted=True,
            manager_act_file=SimpleUploadedFile('manager_act.pdf', b'manager-act-bytes', content_type='application/pdf'),
        )
        self.order.refresh_from_db()
        Act.objects.update_or_create(
            order=self.order, defaults={
                'file': SimpleUploadedFile('act.pdf', b'x', content_type='application/pdf'),
                'uploaded_by': self.manager, 'is_readable_confirmed': True,
            },
        )
        close_order(self.order, self.manager)
        record = PaymentRecord.objects.get(order=self.order)
        self.assertEqual(record.amount, Decimal('10000'))

        # менеджер добавляет доп. работу уже после закрытия заявки
        AdditionalWork.objects.create(order=self.order, description='Забыли учесть', price=Decimal('1200'))
        record.refresh_from_db()
        self.assertEqual(record.amount, Decimal('11200'))

        # но если выплата уже отмечена произведённой — сумму задним числом не трогаем
        mark_payment_paid(record)
        AdditionalWork.objects.create(order=self.order, description='Ещё работа', price=Decimal('300'))
        record.refresh_from_db()
        self.assertEqual(record.amount, Decimal('11200'))


class CollectorAttachesActTests(TestCase):
    """Акт приёма-передачи (п.4 ТЗ) теперь прикрепляет сам сборщик — фото
    подписанного бланка со сдачи заявки, а не отдельный шаг менеджера."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager2', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector2', password='x', role=User.Role.COLLECTOR)
        CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )
        self.template = PhotoSlotTemplate.objects.create(name='Кухня — тест 2')
        self.slot = PhotoSlotDefinition.objects.create(
            template=self.template, title='Общий вид', is_required=True, order=0,
        )
        self.ft = FurnitureType.objects.create(name='Кухня', photo_slots_template=self.template)
        self.order = Order.objects.create(
            furniture_type=self.ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('10000'),
            status=Order.Status.PUBLISHED, created_by=self.manager,
        )
        book_order(self.order.pk, self.collector)
        confirm_booking(self.order.pk, self.manager)
        self.order.refresh_from_db()

    def _submit_with_act(self):
        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        act_photo = SimpleUploadedFile('act.jpg', b'fake-act-bytes', content_type='image/jpeg')
        submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.slot.id: photo}, checked_items=[], comment='Готово',
            act_photo=act_photo,
        )

    def test_act_created_from_collector_submission(self):
        self._submit_with_act()
        act = Act.objects.get(order=self.order)
        self.assertEqual(act.uploaded_by, self.collector)
        self.assertFalse(act.is_readable_confirmed)

    def test_manager_can_confirm_readability_without_reuploading(self):
        self._submit_with_act()
        act = Act.objects.get(order=self.order)
        original_file_name = act.file.name

        client = self.client
        client.force_login(self.manager)
        response = client.post(f'/manager/orders/{self.order.pk}/act/upload/', {'is_readable_confirmed': 'on'})

        act.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(act.is_readable_confirmed)
        self.assertEqual(act.file.name, original_file_name)
        self.assertEqual(act.uploaded_by, self.manager)

    def test_manager_cannot_confirm_without_any_act_or_file(self):
        client = self.client
        client.force_login(self.manager)
        response = client.post(f'/manager/orders/{self.order.pk}/act/upload/', {'is_readable_confirmed': 'on'})

        self.assertFalse(hasattr(self.order, 'act'))
        self.assertEqual(response.status_code, 302)

    def test_resubmission_resets_readability_confirmation(self):
        self._submit_with_act()
        act = Act.objects.get(order=self.order)
        act.is_readable_confirmed = True
        act.save()

        self._submit_with_act()
        act.refresh_from_db()
        self.assertFalse(act.is_readable_confirmed)

    def test_collector_view_submission_creates_act(self):
        """Полный путь через реальную view (не напрямую через сервис) — форма
        должна требовать act_photo и после отправки создавать Act."""
        # ImageField валидирует содержимое через Pillow — нужен настоящий, пусть
        # и крошечный, PNG, а не произвольные байты.
        import io
        from PIL import Image

        def _fake_image(name):
            buf = io.BytesIO()
            Image.new('RGB', (1, 1)).save(buf, format='PNG')
            buf.seek(0)
            return SimpleUploadedFile(name, buf.read(), content_type='image/png')

        client = self.client
        client.force_login(self.collector)

        response = client.post(f'/orders/{self.order.pk}/report/upload/', {
            f'slot_{self.slot.id}': _fake_image('slot.png'),
            'checklist': [],
            'comment': 'Готово',
        })
        # Без act_photo форма должна остаться на странице (невалидна), не редиректить.
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Act.objects.filter(order=self.order).exists())

        response = client.post(f'/orders/{self.order.pk}/report/upload/', {
            f'slot_{self.slot.id}': _fake_image('slot.png'),
            'act_photo': _fake_image('act.png'),
            'checklist': [],
            'comment': 'Готово',
        })
        self.assertEqual(response.status_code, 302)
        act = Act.objects.get(order=self.order)
        self.assertEqual(act.uploaded_by, self.collector)
        self.assertFalse(act.is_readable_confirmed)

    def test_close_order_blocked_without_act_photo_from_collector(self):
        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.slot.id: photo}, checked_items=[], comment='Готово',
        )
        review_photo_report(
            self.order, self.manager, accepted=True,
            manager_act_file=SimpleUploadedFile('manager_act.pdf', b'manager-act-bytes', content_type='application/pdf'),
        )
        self.order.refresh_from_db()

        with self.assertRaises(ValueError):
            close_order(self.order, self.manager)


class ManagerActRequiredTests(TestCase):
    """Менеджер обязан прикрепить свой акт при приёме отчёта — это отдельный
    документ от акта сборщика, сборщик видит его сразу после приёма."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager_act', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector_act', password='x', role=User.Role.COLLECTOR)
        CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )
        self.template = PhotoSlotTemplate.objects.create(name='Кухня — акт менеджера')
        self.slot = PhotoSlotDefinition.objects.create(
            template=self.template, title='Общий вид', is_required=True, order=0,
        )
        self.ft = FurnitureType.objects.create(name='Кухня', photo_slots_template=self.template)
        self.order = Order.objects.create(
            furniture_type=self.ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('10000'),
            status=Order.Status.PUBLISHED, created_by=self.manager,
        )
        book_order(self.order.pk, self.collector)
        confirm_booking(self.order.pk, self.manager)
        self.order.refresh_from_db()

        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        act_photo = SimpleUploadedFile('act.jpg', b'collector-act-bytes', content_type='image/jpeg')
        submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.slot.id: photo}, checked_items=[], comment='Готово', act_photo=act_photo,
        )

    def test_accept_without_manager_act_raises(self):
        with self.assertRaises(ValueError):
            review_photo_report(self.order, self.manager, accepted=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.REPORT_UPLOADED)

    def test_accept_with_manager_act_succeeds(self):
        manager_act = SimpleUploadedFile('manager_act.pdf', b'manager-act-bytes', content_type='application/pdf')
        review_photo_report(self.order, self.manager, accepted=True, manager_act_file=manager_act)
        self.order.refresh_from_db()

        self.assertEqual(self.order.status, Order.Status.ACCEPTED)
        act = Act.objects.get(order=self.order)
        self.assertTrue(act.manager_act_file)
        self.assertIsNotNone(act.manager_act_uploaded_at)
        # акт сборщика и акт менеджера — разные файлы
        self.assertNotEqual(act.file.name, act.manager_act_file.name)

    def test_view_rejects_accept_without_manager_act_file(self):
        client = self.client
        client.force_login(self.manager)
        response = client.post(reverse('report_review', args=[self.order.pk]), {'action': 'accept'})
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.REPORT_UPLOADED)

    def test_view_rejects_disallowed_manager_act_extension(self):
        bad_file = SimpleUploadedFile('act.exe', b'not-an-act', content_type='application/octet-stream')
        client = self.client
        client.force_login(self.manager)
        response = client.post(
            reverse('report_review', args=[self.order.pk]), {'action': 'accept', 'manager_act_file': bad_file},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.REPORT_UPLOADED)

    def test_view_accepts_with_valid_manager_act(self):
        manager_act = SimpleUploadedFile('manager_act.png', b'manager-act-bytes', content_type='image/png')
        client = self.client
        client.force_login(self.manager)
        response = client.post(
            reverse('report_review', args=[self.order.pk]), {'action': 'accept', 'manager_act_file': manager_act},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ACCEPTED)
        self.assertTrue(Act.objects.get(order=self.order).manager_act_file)

    def test_reject_does_not_require_manager_act(self):
        client = self.client
        client.force_login(self.manager)
        response = client.post(
            reverse('report_review', args=[self.order.pk]), {'action': 'reject', 'comment': 'Переснимите'},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.REJECTED_FOR_REWORK)

    def test_collector_sees_manager_act_after_acceptance_before_closure(self):
        manager_act = SimpleUploadedFile('manager_act.pdf', b'manager-act-bytes', content_type='application/pdf')
        review_photo_report(self.order, self.manager, accepted=True, manager_act_file=manager_act)
        self.order.refresh_from_db()

        client = self.client
        client.force_login(self.collector)
        response = client.get(reverse('order_detail', args=[self.order.pk]))
        self.assertContains(response, 'Скачать акт от менеджера')

    def test_collector_does_not_see_manager_act_before_acceptance(self):
        client = self.client
        client.force_login(self.collector)
        response = client.get(reverse('order_detail', args=[self.order.pk]))
        self.assertNotContains(response, 'Скачать акт от менеджера')


class VideoReportTests(TestCase):
    """Видеоотчёт (доп. к фото по слотам) — одно необязательное видео на весь отчёт."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager3', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector3', password='x', role=User.Role.COLLECTOR)
        CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )
        self.template = PhotoSlotTemplate.objects.create(name='Кухня — видео')
        self.slot = PhotoSlotDefinition.objects.create(
            template=self.template, title='Общий вид', is_required=True, order=0,
        )
        self.ft = FurnitureType.objects.create(name='Кухня', photo_slots_template=self.template)
        self.order = Order.objects.create(
            furniture_type=self.ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('10000'),
            status=Order.Status.PUBLISHED, created_by=self.manager,
        )
        book_order(self.order.pk, self.collector)
        confirm_booking(self.order.pk, self.manager)
        self.order.refresh_from_db()

    def test_submit_report_without_video_leaves_field_empty(self):
        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        report = submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.slot.id: photo}, checked_items=[], comment='Готово',
        )
        self.assertFalse(report.video)

    def test_submit_report_with_video_saves_file(self):
        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        video = SimpleUploadedFile('clip.mp4', b'fake-video-bytes', content_type='video/mp4')
        report = submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.slot.id: photo}, checked_items=[], comment='Готово', video=video,
        )
        self.assertTrue(report.video)
        self.assertTrue(report.video.name.endswith('.mp4'))

    def _fake_image(self, name):
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGB', (1, 1)).save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type='image/png')

    def test_form_rejects_disallowed_video_extension(self):
        from .forms import SlotPhotoForm

        photo = self._fake_image('slot.png')
        act_photo = self._fake_image('act.png')
        bad_video = SimpleUploadedFile('clip.exe', b'not-a-video', content_type='application/octet-stream')
        form = SlotPhotoForm(
            slots=[self.slot],
            data={'checklist': []},
            files={f'slot_{self.slot.id}': photo, 'act_photo': act_photo, 'video': bad_video},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('video', form.errors)

    def test_form_accepts_video_with_allowed_extension(self):
        from .forms import SlotPhotoForm

        photo = self._fake_image('slot.png')
        act_photo = self._fake_image('act.png')
        video = SimpleUploadedFile('clip.mov', b'fake-video-bytes', content_type='video/quicktime')
        form = SlotPhotoForm(
            slots=[self.slot],
            data={'checklist': []},
            files={f'slot_{self.slot.id}': photo, 'act_photo': act_photo, 'video': video},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_rejects_oversized_photo(self):
        from .forms import MAX_PHOTO_SIZE_MB, SlotPhotoForm

        oversized = self._fake_image('slot.png')
        oversized.size = (MAX_PHOTO_SIZE_MB + 1) * 1024 * 1024
        act_photo = self._fake_image('act.png')
        form = SlotPhotoForm(
            slots=[self.slot],
            data={'checklist': []},
            files={f'slot_{self.slot.id}': oversized, 'act_photo': act_photo},
        )
        self.assertFalse(form.is_valid())
        self.assertIn(f'slot_{self.slot.id}', form.errors)

    def test_form_rejects_oversized_video(self):
        from .forms import MAX_VIDEO_SIZE_MB, SlotPhotoForm

        photo = self._fake_image('slot.png')
        act_photo = self._fake_image('act.png')
        oversized_video = SimpleUploadedFile('clip.mp4', b'fake-video-bytes', content_type='video/mp4')
        oversized_video.size = (MAX_VIDEO_SIZE_MB + 1) * 1024 * 1024
        form = SlotPhotoForm(
            slots=[self.slot],
            data={'checklist': []},
            files={f'slot_{self.slot.id}': photo, 'act_photo': act_photo, 'video': oversized_video},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('video', form.errors)

    def test_form_accepts_video_within_size_limit(self):
        from .forms import SlotPhotoForm

        photo = self._fake_image('slot.png')
        act_photo = self._fake_image('act.png')
        video = SimpleUploadedFile('clip.mp4', b'fake-video-bytes', content_type='video/mp4')
        form = SlotPhotoForm(
            slots=[self.slot],
            data={'checklist': []},
            files={f'slot_{self.slot.id}': photo, 'act_photo': act_photo, 'video': video},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_review_page_shows_uploaded_video(self):
        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        video = SimpleUploadedFile('clip.mp4', b'fake-video-bytes', content_type='video/mp4')
        submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.slot.id: photo}, checked_items=[], comment='Готово', video=video,
        )
        client = self.client
        client.force_login(self.manager)
        response = client.get(reverse('report_review', args=[self.order.pk]))
        self.assertContains(response, '<video')

    def test_review_page_hides_video_block_when_absent(self):
        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.slot.id: photo}, checked_items=[], comment='Готово',
        )
        client = self.client
        client.force_login(self.manager)
        response = client.get(reverse('report_review', args=[self.order.pk]))
        self.assertNotContains(response, '<video')

    def test_submit_report_with_video_schedules_compression_after_commit(self):
        from unittest.mock import patch

        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        video = SimpleUploadedFile('clip.mp4', b'fake-video-bytes', content_type='video/mp4')

        with patch('apps.reports.services.compress_photo_report_video_async') as mocked:
            with self.captureOnCommitCallbacks(execute=True):
                report = submit_photo_report(
                    order=self.order, collector=self.collector,
                    slot_files={self.slot.id: photo}, checked_items=[], comment='Готово', video=video,
                )
            mocked.assert_called_once_with(report.pk)

    def test_submit_report_without_video_does_not_schedule_compression(self):
        from unittest.mock import patch

        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')

        with patch('apps.reports.services.compress_photo_report_video_async') as mocked:
            with self.captureOnCommitCallbacks(execute=True):
                submit_photo_report(
                    order=self.order, collector=self.collector,
                    slot_files={self.slot.id: photo}, checked_items=[], comment='Готово',
                )
            mocked.assert_not_called()


class VideoCompressionTests(TestCase):
    """apps.reports.video.compress_photo_report_video — синхронная логика сжатия,
    вызывается напрямую (без потока/on_commit) для детерминированности тестов."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager4', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector4', password='x', role=User.Role.COLLECTOR)
        CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )
        self.template = PhotoSlotTemplate.objects.create(name='Кухня — сжатие')
        self.slot = PhotoSlotDefinition.objects.create(
            template=self.template, title='Общий вид', is_required=True, order=0,
        )
        self.ft = FurnitureType.objects.create(name='Кухня', photo_slots_template=self.template)
        self.order = Order.objects.create(
            furniture_type=self.ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('10000'),
            status=Order.Status.PUBLISHED, created_by=self.manager,
        )
        book_order(self.order.pk, self.collector)
        confirm_booking(self.order.pk, self.manager)
        self.order.refresh_from_db()

        photo = SimpleUploadedFile('slot.jpg', b'fake-image-bytes', content_type='image/jpeg')
        video = SimpleUploadedFile('clip.mp4', b'original-video-bytes-0123456789', content_type='video/mp4')
        self.report = submit_photo_report(
            order=self.order, collector=self.collector,
            slot_files={self.slot.id: photo}, checked_items=[], comment='Готово', video=video,
        )

    def test_skips_when_ffmpeg_not_found(self):
        from unittest.mock import patch

        from .video import compress_photo_report_video

        original_name = self.report.video.name
        with patch('apps.reports.video.shutil.which', return_value=None):
            compress_photo_report_video(self.report.pk)

        self.report.refresh_from_db()
        self.assertEqual(self.report.video.name, original_name)

    def test_keeps_original_when_ffmpeg_fails(self):
        import subprocess
        from unittest.mock import patch

        from .video import compress_photo_report_video

        original_name = self.report.video.name
        with patch('apps.reports.video.shutil.which', return_value='/usr/bin/ffmpeg'), \
             patch('apps.reports.video.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'ffmpeg')):
            compress_photo_report_video(self.report.pk)

        self.report.refresh_from_db()
        self.assertEqual(self.report.video.name, original_name)

    def test_keeps_original_when_compressed_not_smaller(self):
        from unittest.mock import patch

        from .video import compress_photo_report_video

        original_name = self.report.video.name

        def fake_run(cmd, **kwargs):
            target_path = cmd[-1]
            with open(target_path, 'wb') as fh:
                fh.write(b'0' * 1000)  # заведомо больше исходных ~32 байт

        with patch('apps.reports.video.shutil.which', return_value='/usr/bin/ffmpeg'), \
             patch('apps.reports.video.subprocess.run', side_effect=fake_run):
            compress_photo_report_video(self.report.pk)

        self.report.refresh_from_db()
        self.assertEqual(self.report.video.name, original_name)

    def test_replaces_video_when_compressed_is_smaller(self):
        from unittest.mock import patch

        from .video import compress_photo_report_video

        original_name = self.report.video.name

        def fake_run(cmd, **kwargs):
            target_path = cmd[-1]
            with open(target_path, 'wb') as fh:
                fh.write(b'x')  # заведомо меньше исходного файла

        with patch('apps.reports.video.shutil.which', return_value='/usr/bin/ffmpeg'), \
             patch('apps.reports.video.subprocess.run', side_effect=fake_run):
            compress_photo_report_video(self.report.pk)

        self.report.refresh_from_db()
        self.assertNotEqual(self.report.video.name, original_name)
        self.assertTrue(self.report.video.name.endswith('.mp4'))
        self.assertEqual(self.report.video.read(), b'x')

    def test_missing_report_does_not_crash(self):
        from unittest.mock import patch

        from .video import compress_photo_report_video

        with patch('apps.reports.video.shutil.which', return_value='/usr/bin/ffmpeg'):
            compress_photo_report_video(999999)  # не существует — не должно падать
