from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views import View

from apps.core.mixins import RoleRequiredMixin

from .bitrix import BitrixError, get_deal_breakdown

User = get_user_model()


class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.MANAGER, User.Role.ADMIN)


class BitrixDealPriceView(ManagerRequiredMixin, View):
    """AJAX: вернуть разбивку стоимости сделки Bitrix24 по её номеру — для кнопки
    «Подтянуть цену» на форме создания заявки (Сумма изделия, Процент сборки,
    Монтаж, Доп. услуги, Подъём, Доставка + посчитанные Итого и выплата сборщику)."""

    def get(self, request):
        deal_id = request.GET.get('deal_id', '')
        try:
            data = get_deal_breakdown(deal_id)
        except BitrixError as exc:
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

        assembly_amount = (data['item_amount'] * data['assembly_percent'] / Decimal('100')).quantize(Decimal('0.01'))
        total = (
            data['item_amount'] + assembly_amount + data['installation_amount']
            + data['additional_services_amount'] + data['lift_amount'] + data['delivery_amount']
        )
        payout = assembly_amount + data['installation_amount'] + data['additional_services_amount']

        return JsonResponse({
            'ok': True,
            'title': data['title'],
            'item_amount': str(data['item_amount']),
            'assembly_percent': str(data['assembly_percent']),
            'assembly_amount': str(assembly_amount),
            'installation_amount': str(data['installation_amount']),
            'additional_services_amount': str(data['additional_services_amount']),
            'lift_amount': str(data['lift_amount']),
            'delivery_amount': str(data['delivery_amount']),
            'total': str(total),
            'payout': str(payout),
        })
