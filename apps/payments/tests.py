import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.collectors.models import CollectorProfile
from apps.dictionaries.models import FurnitureType
from apps.orders.models import Order

from .models import PaymentRecord, WithdrawalRequest
from .services import (
    WithdrawalRequestError,
    cancel_withdrawal_request,
    complete_withdrawal_request,
    create_payment_record,
    create_withdrawal_request,
    mark_payment_paid,
    rate_collector,
)

User = get_user_model()


class RatingAndPaymentTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector', password='x', role=User.Role.COLLECTOR)
        CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
        )
        ft = FurnitureType.objects.create(name='Кухня')
        self.order = Order.objects.create(
            furniture_type=ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('8000'),
            status=Order.Status.CLOSED, created_by=self.manager, collector=self.collector,
        )

    def test_cannot_rate_collector_on_non_closed_order(self):
        self.order.status = Order.Status.IN_PROGRESS
        self.order.save()
        with self.assertRaises(ValueError):
            rate_collector(self.order, self.manager, score=5, deadline_met=True, had_complaint=False)

    def test_rate_collector_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            rate_collector(self.order, self.manager, score=6, deadline_met=True, had_complaint=False)

    def test_rate_collector_success_updates_average(self):
        rate_collector(self.order, self.manager, score=4, deadline_met=True, had_complaint=False, comment='Хорошо')
        profile = CollectorProfile.objects.get(user=self.collector)
        self.assertEqual(profile.average_rating, 4)
        self.assertEqual(profile.ratings_count, 1)

    def test_re_rating_same_order_updates_not_duplicates(self):
        rate_collector(self.order, self.manager, score=3, deadline_met=True, had_complaint=False)
        rate_collector(self.order, self.manager, score=5, deadline_met=True, had_complaint=False)
        profile = CollectorProfile.objects.get(user=self.collector)
        self.assertEqual(profile.ratings_count, 1)
        self.assertEqual(profile.average_rating, 5)

    def test_create_payment_record_uses_total_price(self):
        record = create_payment_record(self.order)
        self.assertEqual(record.amount, self.order.total_price)
        self.assertFalse(record.is_paid)

    def test_create_payment_record_idempotent(self):
        create_payment_record(self.order)
        create_payment_record(self.order)
        self.assertEqual(PaymentRecord.objects.filter(order=self.order).count(), 1)

    def test_mark_payment_paid(self):
        record = create_payment_record(self.order)
        mark_payment_paid(record)
        record.refresh_from_db()
        self.assertTrue(record.is_paid)
        self.assertIsNotNone(record.paid_at)


class WithdrawalRequestTests(TestCase):
    """Сборщик запрашивает вывод баланса; менеджер видит заявку и завершает выплату."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='collector', password='x', role=User.Role.COLLECTOR)
        CollectorProfile.objects.create(
            user=self.collector, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
        )
        ft = FurnitureType.objects.create(name='Кухня')
        self.order = Order.objects.create(
            furniture_type=ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('8000'),
            status=Order.Status.CLOSED, created_by=self.manager, collector=self.collector,
        )
        create_payment_record(self.order)

    def test_cannot_request_withdrawal_without_balance(self):
        collector_without_balance = User.objects.create_user(username='nobody', password='x', role=User.Role.COLLECTOR)
        with self.assertRaises(WithdrawalRequestError):
            create_withdrawal_request(collector_without_balance, method=WithdrawalRequest.Method.IN_PERSON)

    def test_card_transfer_requires_requisite(self):
        """Проверка требования реквизитов — на уровне сервиса минимальная, форма делает основную валидацию."""
        wr = create_withdrawal_request(
            self.collector, method=WithdrawalRequest.Method.CARD_TRANSFER, requisite='1234 5678',
        )
        self.assertEqual(wr.requisite, '1234 5678')

    def test_withdrawal_request_captures_full_balance(self):
        wr = create_withdrawal_request(self.collector, method=WithdrawalRequest.Method.IN_PERSON)
        self.assertEqual(wr.amount, Decimal('8000'))
        self.assertEqual(wr.status, WithdrawalRequest.Status.PENDING)
        self.assertEqual(list(wr.payment_records.all()), [PaymentRecord.objects.get(order=self.order)])

    def test_cannot_create_second_pending_request(self):
        create_withdrawal_request(self.collector, method=WithdrawalRequest.Method.IN_PERSON)
        with self.assertRaises(WithdrawalRequestError):
            create_withdrawal_request(self.collector, method=WithdrawalRequest.Method.CARD_TRANSFER, requisite='x')

    def test_complete_withdrawal_marks_payment_records_paid(self):
        wr = create_withdrawal_request(self.collector, method=WithdrawalRequest.Method.PHONE_TRANSFER, requisite='+79990001122')
        complete_withdrawal_request(wr, self.manager)

        wr.refresh_from_db()
        record = PaymentRecord.objects.get(order=self.order)

        self.assertEqual(wr.status, WithdrawalRequest.Status.COMPLETED)
        self.assertEqual(wr.handled_by, self.manager)
        self.assertTrue(record.is_paid)

    def test_cancel_withdrawal_does_not_mark_paid(self):
        wr = create_withdrawal_request(self.collector, method=WithdrawalRequest.Method.IN_PERSON)
        cancel_withdrawal_request(wr, self.manager, reason='Не дозвонились')

        wr.refresh_from_db()
        record = PaymentRecord.objects.get(order=self.order)

        self.assertEqual(wr.status, WithdrawalRequest.Status.CANCELLED)
        self.assertFalse(record.is_paid)

    def test_cannot_complete_already_completed_request(self):
        wr = create_withdrawal_request(self.collector, method=WithdrawalRequest.Method.IN_PERSON)
        complete_withdrawal_request(wr, self.manager)
        with self.assertRaises(WithdrawalRequestError):
            complete_withdrawal_request(wr, self.manager)

    def test_new_request_can_be_created_after_previous_completed(self):
        wr = create_withdrawal_request(self.collector, method=WithdrawalRequest.Method.IN_PERSON)
        complete_withdrawal_request(wr, self.manager)

        # новый закрытый заказ -> новый баланс -> новая заявка должна проходить
        ft = FurnitureType.objects.first()
        order2 = Order.objects.create(
            furniture_type=ft, address='ул. Тестовая, 2', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('2000'),
            status=Order.Status.CLOSED, created_by=self.manager, collector=self.collector,
        )
        create_payment_record(order2)

        wr2 = create_withdrawal_request(self.collector, method=WithdrawalRequest.Method.IN_PERSON)
        self.assertEqual(wr2.amount, Decimal('2000'))
