from django.urls import path

from .views import (
    MarkPaymentPaidView,
    PaymentHistoryView,
    RateCollectorView,
    WithdrawalRequestCompleteView,
    WithdrawalRequestCreateView,
    WithdrawalRequestListView,
)

urlpatterns = [
    path('manager/orders/<int:pk>/rate/', RateCollectorView.as_view(), name='rate_collector'),
    path('manager/orders/<int:pk>/mark-paid/', MarkPaymentPaidView.as_view(), name='mark_payment_paid'),
    path('payments/history/', PaymentHistoryView.as_view(), name='payment_history'),

    path('payments/withdraw/', WithdrawalRequestCreateView.as_view(), name='withdrawal_request_create'),
    path('manager/withdrawal-requests/', WithdrawalRequestListView.as_view(), name='withdrawal_requests_list'),
    path(
        'manager/withdrawal-requests/<int:pk>/complete/',
        WithdrawalRequestCompleteView.as_view(), name='withdrawal_request_complete',
    ),
]
