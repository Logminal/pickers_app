from django.urls import path

from .views import MarkPaymentPaidView, PaymentHistoryView, RateCollectorView

urlpatterns = [
    path('manager/orders/<int:pk>/rate/', RateCollectorView.as_view(), name='rate_collector'),
    path('manager/orders/<int:pk>/mark-paid/', MarkPaymentPaidView.as_view(), name='mark_payment_paid'),
    path('payments/history/', PaymentHistoryView.as_view(), name='payment_history'),
]
