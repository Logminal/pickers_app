import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.collectors.models import CollectorProfile
from apps.dictionaries.models import FurnitureType

from .models import Order
from .services import (
    ACTIVE_BOOKING_STATUSES,
    OrderBookingError,
    book_order,
    cancel_order,
    confirm_booking,
    reject_booking,
    revoke_booking,
)

User = get_user_model()


class OrderBookingTests(TestCase):
    """Бронирование заявки — самое рискованное место в системе (гонка, лимиты)."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.ft = FurnitureType.objects.create(name='Кухня')

    def _make_collector(self, username):
        user = User.objects.create_user(username=username, password='x', role=User.Role.COLLECTOR)
        CollectorProfile.objects.create(
            user=user, full_name='Тест Тестов', birth_date='1990-01-01', birth_place='М',
            status=CollectorProfile.Status.CONFIRMED,
        )
        return user

    def _make_order(self, status=Order.Status.PUBLISHED, collector=None):
        return Order.objects.create(
            furniture_type=self.ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=10000,
            status=status, created_by=self.manager, collector=collector,
        )

    def test_book_order_success(self):
        collector = self._make_collector('col1')
        order = self._make_order()

        book_order(order.pk, collector)
        order.refresh_from_db()

        self.assertEqual(order.status, Order.Status.BOOKED)
        self.assertEqual(order.collector, collector)
        self.assertIsNotNone(order.booked_at)

    def test_cannot_book_already_booked_order(self):
        """Второй сборщик не может забронировать уже занятую заявку — защита от гонки."""
        first_collector = self._make_collector('col1')
        second_collector = self._make_collector('col2')
        order = self._make_order()

        book_order(order.pk, first_collector)

        with self.assertRaises(OrderBookingError):
            book_order(order.pk, second_collector)

        order.refresh_from_db()
        self.assertEqual(order.collector, first_collector)

    def test_cannot_book_beyond_max_active_bookings(self):
        collector = self._make_collector('col1')
        with self.settings(MAX_ACTIVE_BOOKINGS_PER_COLLECTOR=2):
            for _ in range(2):
                order = self._make_order()
                book_order(order.pk, collector)

            over_limit_order = self._make_order()
            with self.assertRaises(OrderBookingError):
                book_order(over_limit_order.pk, collector)

            over_limit_order.refresh_from_db()
            self.assertIsNone(over_limit_order.collector)

    def test_closed_orders_do_not_count_toward_limit(self):
        collector = self._make_collector('col1')
        with self.settings(MAX_ACTIVE_BOOKINGS_PER_COLLECTOR=1):
            closed_order = self._make_order(status=Order.Status.CLOSED, collector=collector)
            self.assertNotIn(closed_order.status, ACTIVE_BOOKING_STATUSES)

            new_order = self._make_order()
            book_order(new_order.pk, collector)  # не должно упасть — closed не считается активной
            new_order.refresh_from_db()
            self.assertEqual(new_order.status, Order.Status.BOOKED)

    def test_confirm_booking_requires_booked_status(self):
        order = self._make_order(status=Order.Status.PUBLISHED)
        with self.assertRaises(OrderBookingError):
            confirm_booking(order.pk, self.manager)

    def test_confirm_booking_success(self):
        collector = self._make_collector('col1')
        order = self._make_order()
        book_order(order.pk, collector)

        confirm_booking(order.pk, self.manager)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_reject_booking_does_not_block_collector(self):
        collector = self._make_collector('col1')
        order = self._make_order()
        book_order(order.pk, collector)

        reject_booking(order.pk, self.manager, reason='Сомнения')
        order.refresh_from_db()
        profile = CollectorProfile.objects.get(user=collector)

        self.assertEqual(order.status, Order.Status.PUBLISHED)
        self.assertIsNone(order.collector)
        self.assertEqual(profile.status, CollectorProfile.Status.CONFIRMED)  # не заблокирован

    def test_revoke_booking_returns_order_to_pool(self):
        collector = self._make_collector('col1')
        order = self._make_order()
        book_order(order.pk, collector)
        confirm_booking(order.pk, self.manager)

        revoke_booking(order.pk, self.manager, reason='Пропал')
        order.refresh_from_db()

        self.assertEqual(order.status, Order.Status.PUBLISHED)
        self.assertIsNone(order.collector)

    def test_cancel_order(self):
        order = self._make_order()
        cancel_order(order.pk, self.manager, reason='Клиент отказался')
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)


class OrderCreateFormPriceValidationTests(TestCase):
    """Поле «Стоимость» должно принимать только положительные числа."""

    def setUp(self):
        self.ft = FurnitureType.objects.create(name='Кухня')

    def _form_data(self, price):
        now = timezone.now()
        return {
            'furniture_type': self.ft.id, 'address': 'ул. Тестовая, 1',
            'scheduled_at': now.strftime('%Y-%m-%dT%H:%M'),
            'deadline_at': (now + datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'urgency': 'normal', 'price': price,
        }

    def test_negative_price_rejected(self):
        from .forms import OrderCreateForm
        form = OrderCreateForm(self._form_data('-500'))
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_zero_price_rejected(self):
        from .forms import OrderCreateForm
        form = OrderCreateForm(self._form_data('0'))
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_non_numeric_price_rejected(self):
        from .forms import OrderCreateForm
        form = OrderCreateForm(self._form_data('много денег'))
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_valid_positive_price_accepted(self):
        from .forms import OrderCreateForm
        form = OrderCreateForm(self._form_data('15000.50'))
        self.assertNotIn('price', form.errors)
