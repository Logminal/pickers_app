from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from .bitrix import BitrixError, get_deal_breakdown, get_deal_price

User = get_user_model()


def _deal_response(**overrides):
    data = {
        'ID': '5', 'TITLE': 'Тест',
        'OPPORTUNITY': '9100.00000000', 'CURRENCY_ID': 'RUB',
        'UF_CRM_1782215090557': '80000|RUB',
        'UF_CRM_1782216015647': '15',
        'UF_CRM_1612863263941': '5000|RUB',
        'UF_CRM_1782220049586': '2000|RUB',
        'UF_CRM_5D56732C52940': '1000|RUB',
        'UF_CRM_1553148181482': '2500|RUB',
    }
    data.update(overrides)
    return Mock(ok=True, status_code=200, json=lambda: {'result': data})


@override_settings(BITRIX_WEBHOOK_URL='https://example.bitrix24.ru/rest/1/faketoken/')
class BitrixClientTests(TestCase):
    @patch('apps.integrations.bitrix.requests.get')
    def test_successful_price_fetch(self, mock_get):
        mock_get.return_value = _deal_response()

        result = get_deal_price('5')

        self.assertEqual(result['price'], Decimal('9100.00000000'))
        self.assertEqual(result['currency'], 'RUB')

    @patch('apps.integrations.bitrix.requests.get')
    def test_deal_not_found_raises_readable_error(self, mock_get):
        mock_get.return_value = Mock(
            ok=False, status_code=400,
            json=lambda: {'error': '', 'error_description': 'Not found'},
        )

        with self.assertRaises(BitrixError) as ctx:
            get_deal_price('999999999')
        self.assertIn('Not found', str(ctx.exception))

    @patch('apps.integrations.bitrix.requests.get')
    def test_zero_price_rejected(self, mock_get):
        mock_get.return_value = _deal_response(OPPORTUNITY='0')

        with self.assertRaises(BitrixError):
            get_deal_price('5')

    def test_non_numeric_deal_id_rejected_without_network_call(self):
        with self.assertRaises(BitrixError):
            get_deal_price('not-a-number')

    @override_settings(BITRIX_WEBHOOK_URL='')
    def test_missing_webhook_config_raises_clear_error(self):
        with self.assertRaises(BitrixError) as ctx:
            get_deal_price('5')
        self.assertIn('не настроена', str(ctx.exception))

    @patch('apps.integrations.bitrix.requests.get')
    def test_breakdown_parses_all_components(self, mock_get):
        mock_get.return_value = _deal_response()

        result = get_deal_breakdown('5')

        self.assertEqual(result['item_amount'], Decimal('80000'))
        self.assertEqual(result['assembly_percent'], Decimal('15'))
        self.assertEqual(result['installation_amount'], Decimal('5000'))
        self.assertEqual(result['additional_services_amount'], Decimal('2000'))
        self.assertEqual(result['lift_amount'], Decimal('1000'))
        self.assertEqual(result['delivery_amount'], Decimal('2500'))

    @patch('apps.integrations.bitrix.requests.get')
    def test_breakdown_missing_installation_and_lift_defaults_to_zero(self, mock_get):
        mock_get.return_value = _deal_response(
            **{'UF_CRM_1612863263941': '', 'UF_CRM_5D56732C52940': ''}
        )

        result = get_deal_breakdown('5')

        self.assertEqual(result['installation_amount'], Decimal('0'))
        self.assertEqual(result['lift_amount'], Decimal('0'))

    @patch('apps.integrations.bitrix.requests.get')
    def test_breakdown_missing_item_amount_raises_error(self, mock_get):
        mock_get.return_value = _deal_response(**{'UF_CRM_1782215090557': ''})

        with self.assertRaises(BitrixError) as ctx:
            get_deal_breakdown('5')
        self.assertIn('Общая сумма изделия', str(ctx.exception))


@override_settings(BITRIX_WEBHOOK_URL='https://example.bitrix24.ru/rest/1/faketoken/')
class BitrixDealPriceViewTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username='mgr', password='x', role=User.Role.MANAGER)
        self.collector = User.objects.create_user(username='col', password='x', role=User.Role.COLLECTOR)

    @patch('apps.integrations.views.get_deal_breakdown')
    def test_manager_can_fetch_breakdown(self, mock_get_breakdown):
        mock_get_breakdown.return_value = {
            'title': 'Тест',
            'item_amount': Decimal('80000'),
            'assembly_percent': Decimal('15'),
            'installation_amount': Decimal('5000'),
            'additional_services_amount': Decimal('2000'),
            'lift_amount': Decimal('1000'),
            'delivery_amount': Decimal('2500'),
        }
        client = Client()
        client.force_login(self.manager)

        response = client.get('/manager/bitrix/deal-price/', {'deal_id': '5'})
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(data['assembly_amount'], '12000.00')  # 80000 * 15%
        self.assertEqual(data['total'], '102500.00')  # 80000+12000+5000+2000+1000+2500
        self.assertEqual(data['payout'], '19000.00')  # 12000+5000+2000

    def test_collector_forbidden(self):
        client = Client()
        client.force_login(self.collector)
        response = client.get('/manager/bitrix/deal-price/', {'deal_id': '5'})
        self.assertEqual(response.status_code, 403)

    def test_anonymous_redirected(self):
        client = Client()
        response = client.get('/manager/bitrix/deal-price/', {'deal_id': '5'})
        self.assertEqual(response.status_code, 302)

    @patch('apps.integrations.views.get_deal_breakdown')
    def test_bitrix_error_returns_400_with_message(self, mock_get_breakdown):
        mock_get_breakdown.side_effect = BitrixError('Сделка не найдена')
        client = Client()
        client.force_login(self.manager)

        response = client.get('/manager/bitrix/deal-price/', {'deal_id': '999'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['ok'], False)
        self.assertIn('не найдена', response.json()['error'])
