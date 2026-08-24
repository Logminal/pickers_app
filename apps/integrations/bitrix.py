"""Синхронизация цены из Bitrix24 (п.8 ТЗ) — входящий вебхук, REST API.

Разбивка стоимости (уточнено с заказчиком) тянется из полей сделки категории
«Производство Корпусной мебели»:
  UF_CRM_1782215090557 — «Общая сумма изделия Ecxel» (Сумма изделия)
  UF_CRM_1782216015647 — «Процент цех» (Процент сборки, %)
  UF_CRM_1612863263941 — «Монтаж»
  UF_CRM_1782220049586 — «Доп. стоимость» (Доп. услуги)
  UF_CRM_1557304350 — «Сумма подъёма»
  UF_CRM_1553148181482 — «Доставка»

Итого = сумма всех компонентов (считаем сами, складывая всё).
Синхронизация разовая, по кнопке — менеджер вводит номер сделки при создании
заявки и подтягивает актуальную цену и разбивку вручную.
"""

from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings

BREAKDOWN_FIELD_CODES = {
    'item_amount': 'UF_CRM_1782215090557',
    'assembly_percent': 'UF_CRM_1782216015647',
    'installation_amount': 'UF_CRM_1612863263941',
    'additional_services_amount': 'UF_CRM_1782220049586',
    'lift_amount': 'UF_CRM_1557304350',
    'delivery_amount': 'UF_CRM_1553148181482',
}


class BitrixError(Exception):
    pass


def _fetch_deal(deal_id: str) -> dict:
    """Возвращает сырой словарь полей сделки по номеру. Бросает BitrixError
    с понятным сообщением, если сделка не найдена или интеграция не настроена."""

    if not settings.BITRIX_WEBHOOK_URL:
        raise BitrixError('Интеграция с Bitrix24 не настроена (нет BITRIX_WEBHOOK_URL в .env).')

    deal_id = str(deal_id).strip()
    if not deal_id.isdigit():
        raise BitrixError('Номер сделки должен быть числом.')

    url = settings.BITRIX_WEBHOOK_URL.rstrip('/') + '/crm.deal.get.json'
    try:
        response = requests.get(url, params={'id': deal_id}, timeout=10)
    except requests.RequestException as exc:
        raise BitrixError(f'Не удалось связаться с Bitrix24: {exc}') from exc

    # Bitrix24 на ошибку (например, "сделка не найдена") может вернуть как 200,
    # так и 400 — в обоих случаях тело содержит error/error_description, поэтому
    # сначала пробуем прочитать JSON и только потом смотрим на HTTP-статус.
    try:
        data = response.json()
    except ValueError:
        data = None

    if data and data.get('error'):
        raise BitrixError(f'Bitrix24: {data.get("error_description") or data["error"]}')
    if data and 'error_description' in data and not data.get('result'):
        raise BitrixError(f'Сделка #{deal_id} не найдена в Bitrix24: {data["error_description"]}')

    if not response.ok:
        raise BitrixError(f'Bitrix24 вернул ошибку {response.status_code}.')

    deal = data.get('result') if data else None
    if not deal:
        raise BitrixError(f'Сделка #{deal_id} не найдена в Bitrix24.')

    return deal


def _parse_money(value) -> Decimal | None:
    if value in (None, ''):
        return None
    text = str(value)
    if '|' in text:
        text = text.split('|', 1)[0]
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def get_deal_price(deal_id: str) -> dict:
    """Возвращает {'price': Decimal, 'title': str, 'currency': str} по номеру сделки."""

    deal = _fetch_deal(deal_id)

    price = _parse_money(deal.get('OPPORTUNITY'))
    if price is None:
        raise BitrixError(f'У сделки #{deal_id} некорректная цена в Bitrix24.')
    if price <= 0:
        raise BitrixError(f'У сделки #{deal_id} не указана сумма в Bitrix24.')

    return {
        'price': price,
        'title': deal.get('TITLE', ''),
        'currency': deal.get('CURRENCY_ID', ''),
    }


def get_deal_breakdown(deal_id: str) -> dict:
    """Возвращает разбивку стоимости по номеру сделки:
    {'title', 'item_amount', 'assembly_percent', 'installation_amount',
     'additional_services_amount', 'lift_amount', 'delivery_amount'}.
    Деньги — Decimal, процент — Decimal. Незаполненные денежные поля считаем
    нулём (не в каждой заявке есть монтаж/подъём/доставка)."""

    deal = _fetch_deal(deal_id)

    item_amount = _parse_money(deal.get(BREAKDOWN_FIELD_CODES['item_amount']))
    if item_amount is None:
        raise BitrixError(
            f'У сделки #{deal_id} не заполнено поле «Общая сумма изделия Ecxel» в Bitrix24.'
        )

    assembly_percent_raw = deal.get(BREAKDOWN_FIELD_CODES['assembly_percent'])
    try:
        assembly_percent = Decimal(str(assembly_percent_raw)) if assembly_percent_raw not in (None, '') else Decimal('0')
    except InvalidOperation:
        assembly_percent = Decimal('0')

    result = {
        'title': deal.get('TITLE', ''),
        'item_amount': item_amount,
        'assembly_percent': assembly_percent,
        'installation_amount': _parse_money(deal.get(BREAKDOWN_FIELD_CODES['installation_amount'])) or Decimal('0'),
        'additional_services_amount': _parse_money(deal.get(BREAKDOWN_FIELD_CODES['additional_services_amount'])) or Decimal('0'),
        'lift_amount': _parse_money(deal.get(BREAKDOWN_FIELD_CODES['lift_amount'])) or Decimal('0'),
        'delivery_amount': _parse_money(deal.get(BREAKDOWN_FIELD_CODES['delivery_amount'])) or Decimal('0'),
    }
    return result
