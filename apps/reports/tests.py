import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
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
        review_photo_report(self.order, self.manager, accepted=True)
        self.order.refresh_from_db()

        with self.assertRaises(ValueError):
            close_order(self.order, self.manager)

    def test_cannot_close_order_with_unconfirmed_act_readability(self):
        self._submit_report()
        review_photo_report(self.order, self.manager, accepted=True)
        self.order.refresh_from_db()

        Act.objects.create(
            order=self.order, file=SimpleUploadedFile('act.pdf', b'x', content_type='application/pdf'),
            uploaded_by=self.manager, is_readable_confirmed=False,
        )

        with self.assertRaises(ValueError):
            close_order(self.order, self.manager)

    def test_close_order_succeeds_with_confirmed_readable_act(self):
        self._submit_report()
        review_photo_report(self.order, self.manager, accepted=True)
        self.order.refresh_from_db()

        Act.objects.create(
            order=self.order, file=SimpleUploadedFile('act.pdf', b'x', content_type='application/pdf'),
            uploaded_by=self.manager, is_readable_confirmed=True,
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
        review_photo_report(self.order, self.manager, accepted=True)
        self.order.refresh_from_db()
        Act.objects.create(
            order=self.order, file=SimpleUploadedFile('act.pdf', b'x', content_type='application/pdf'),
            uploaded_by=self.manager, is_readable_confirmed=True,
        )
        close_order(self.order, self.manager)

        record = PaymentRecord.objects.get(order=self.order)
        self.assertEqual(record.amount, Decimal('10500'))
        self.assertFalse(record.is_paid)

    def test_payment_record_syncs_when_additional_work_added_after_closure(self):
        from apps.payments.models import PaymentRecord
        from apps.payments.services import mark_payment_paid

        self._submit_report()
        review_photo_report(self.order, self.manager, accepted=True)
        self.order.refresh_from_db()
        Act.objects.create(
            order=self.order, file=SimpleUploadedFile('act.pdf', b'x', content_type='application/pdf'),
            uploaded_by=self.manager, is_readable_confirmed=True,
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
        review_photo_report(self.order, self.manager, accepted=True)
        self.order.refresh_from_db()

        with self.assertRaises(ValueError):
            close_order(self.order, self.manager)
