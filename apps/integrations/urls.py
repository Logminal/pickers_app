from django.urls import path

from .views import BitrixDealPriceView

urlpatterns = [
    path('manager/bitrix/deal-price/', BitrixDealPriceView.as_view(), name='bitrix_deal_price'),
]
