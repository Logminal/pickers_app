import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.collectors.models import CollectorProfile
from apps.dictionaries.models import FurnitureType
from apps.orders.models import Order

from .models import PaymentRecord
from .services import create_payment_record, mark_payment_paid, rate_collector

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
