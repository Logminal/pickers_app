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


class AnalyticsTotalClosedValueTests(TestCase):
    """Финансовая сводка должна учитывать доп. работы, а не только базовую цену заявки."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.ft = FurnitureType.objects.create(name='Кухня')

    def test_total_closed_value_includes_additional_works(self):
        from decimal import Decimal

        from apps.reports.models import AdditionalWork

        order = Order.objects.create(
            furniture_type=self.ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=Decimal('10000'),
            status=Order.Status.CLOSED, created_by=self.manager,
        )
        AdditionalWork.objects.create(order=order, description='Доп. работа', price=Decimal('2500'))

        self.client.force_login(self.manager)
        response = self.client.get('/manager/analytics/')

        self.assertEqual(response.context['total_closed_value'], Decimal('12500'))


class NewOrderNotificationTests(TestCase):
    """Новая подходящая заявка (п.6 ТЗ) — уведомление подтверждённым сборщикам при создании."""

    def setUp(self):
        from apps.dictionaries.models import Specialization

        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.ft = FurnitureType.objects.create(name='Кухня')
        self.spec = Specialization.objects.create(name='Кухни')

    def _make_collector(self, username, status, specializations=()):
        user = User.objects.create_user(username=username, password='x', role=User.Role.COLLECTOR)
        profile = CollectorProfile.objects.create(
            user=user, full_name='Тест', birth_date='1990-01-01', birth_place='М', status=status,
        )
        if specializations:
            profile.specializations.set(specializations)
        return user

    def test_confirmed_collector_with_matching_specialization_notified(self):
        from apps.notifications.models import NotificationLog

        collector = self._make_collector('c1', CollectorProfile.Status.CONFIRMED, [self.spec])
        self.client.force_login(self.manager)

        self.client.post('/manager/orders/create/', {
            'furniture_type': self.ft.id, 'address': 'ул. Тест, 1',
            'scheduled_at': '2026-06-01T10:00', 'deadline_at': '2026-06-02T10:00',
            'urgency': 'normal', 'price': '5000', 'required_specialization': self.spec.id,
        })

        self.assertTrue(
            NotificationLog.objects.filter(user=collector, event_type='new_matching_order').exists()
        )

    def test_collector_with_different_specialization_not_notified(self):
        from apps.dictionaries.models import Specialization
        from apps.notifications.models import NotificationLog

        other_spec = Specialization.objects.create(name='Шкафы-купе')
        collector = self._make_collector('c2', CollectorProfile.Status.CONFIRMED, [other_spec])
        self.client.force_login(self.manager)

        self.client.post('/manager/orders/create/', {
            'furniture_type': self.ft.id, 'address': 'ул. Тест, 2',
            'scheduled_at': '2026-06-01T10:00', 'deadline_at': '2026-06-02T10:00',
            'urgency': 'normal', 'price': '5000', 'required_specialization': self.spec.id,
        })

        self.assertFalse(
            NotificationLog.objects.filter(user=collector, event_type='new_matching_order').exists()
        )

    def test_unconfirmed_collector_not_notified(self):
        from apps.notifications.models import NotificationLog

        collector = self._make_collector('c3', CollectorProfile.Status.UNDER_REVIEW, [self.spec])
        self.client.force_login(self.manager)

        self.client.post('/manager/orders/create/', {
            'furniture_type': self.ft.id, 'address': 'ул. Тест, 3',
            'scheduled_at': '2026-06-01T10:00', 'deadline_at': '2026-06-02T10:00',
            'urgency': 'normal', 'price': '5000', 'required_specialization': self.spec.id,
        })

        self.assertFalse(
            NotificationLog.objects.filter(user=collector, event_type='new_matching_order').exists()
        )

    def test_order_without_specialization_requirement_notifies_all_confirmed(self):
        from apps.notifications.models import NotificationLog

        collector = self._make_collector('c4', CollectorProfile.Status.CONFIRMED)
        self.client.force_login(self.manager)

        self.client.post('/manager/orders/create/', {
            'furniture_type': self.ft.id, 'address': 'ул. Тест, 4',
            'scheduled_at': '2026-06-01T10:00', 'deadline_at': '2026-06-02T10:00',
            'urgency': 'normal', 'price': '5000',
        })

        self.assertTrue(
            NotificationLog.objects.filter(user=collector, event_type='new_matching_order').exists()
        )


class BitrixPayoutCalculationTests(TestCase):
    """Выплата сборщику из разбивки Bitrix24 (уточнено с заказчиком):
    процент сборки (в деньгах) + монтаж + доп. услуги — НЕ полная стоимость."""

    def setUp(self):
        self.manager = User.objects.create_user(username='manager', password='x', role=User.Role.MANAGER)
        self.ft = FurnitureType.objects.create(name='Кухня')

    def _make_order(self, **breakdown):
        return Order.objects.create(
            furniture_type=self.ft, address='ул. Тестовая, 1', scheduled_at=timezone.now(),
            deadline_at=timezone.now() + datetime.timedelta(days=1), price=100000,
            status=Order.Status.PUBLISHED, created_by=self.manager, **breakdown,
        )

    def test_no_breakdown_falls_back_to_total_price(self):
        order = self._make_order()

        self.assertIsNone(order.collector_payout_amount)
        self.assertEqual(order.collector_payout_total, order.total_price)

    def test_payout_is_assembly_percent_plus_installation_plus_additional_services(self):
        order = self._make_order(
            bitrix_item_amount=80000, bitrix_assembly_percent=15,
            bitrix_installation_amount=5000, bitrix_additional_services_amount=2000,
            bitrix_lift_amount=1000, bitrix_delivery_amount=2500,
        )

        self.assertEqual(order.bitrix_assembly_amount, 12000)
        self.assertEqual(order.bitrix_total, 80000 + 12000 + 5000 + 2000 + 1000 + 2500)
        self.assertEqual(order.collector_payout_amount, 12000 + 5000 + 2000)
        self.assertNotIn(order.collector_payout_amount, [order.bitrix_total, order.price])

    def test_payout_ignores_item_amount_lift_and_delivery(self):
        """Ключевая проверка: 'Сумма изделия', 'Подъем' и 'Доставка' НЕ входят в выплату сборщику."""
        cheap_item = self._make_order(
            bitrix_item_amount=1000, bitrix_assembly_percent=10,
            bitrix_installation_amount=3000, bitrix_additional_services_amount=0,
            bitrix_lift_amount=99999, bitrix_delivery_amount=99999,
        )
        self.assertEqual(cheap_item.collector_payout_amount, 100 + 3000)

    def test_payout_total_includes_onsite_additional_work(self):
        from apps.reports.models import AdditionalWork

        order = self._make_order(
            bitrix_item_amount=80000, bitrix_assembly_percent=15,
            bitrix_installation_amount=5000, bitrix_additional_services_amount=2000,
        )
        AdditionalWork.objects.create(order=order, description='Доп. работа на месте', price=1500)

        self.assertEqual(order.collector_payout_total, 12000 + 5000 + 2000 + 1500)

    def test_zero_assembly_percent_does_not_contribute_to_payout(self):
        """Процент сборки = 0% -> в ЗП монтажника идёт только монтаж + доп. услуги,
        без вклада от суммы изделия."""
        order = self._make_order(
            bitrix_item_amount=80000, bitrix_assembly_percent=0,
            bitrix_installation_amount=5000, bitrix_additional_services_amount=2000,
            bitrix_lift_amount=1000, bitrix_delivery_amount=2500,
        )

        self.assertEqual(order.bitrix_assembly_amount, 0)
        self.assertEqual(order.collector_payout_amount, 5000 + 2000)
