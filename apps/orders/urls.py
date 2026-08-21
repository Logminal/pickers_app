from django.urls import path

from .views import (
    AnalyticsDashboardView,
    ManagerOrderDetailView,
    ManagerOrderListView,
    MyOrdersView,
    OrderBookView,
    OrderCancelView,
    OrderConfirmBookingView,
    OrderCreateView,
    OrderDetailView,
    OrderListView,
    OrderRejectBookingView,
    OrderRevokeAndBlockView,
)

urlpatterns = [
    path('', OrderListView.as_view(), name='order_list'),
    path('orders/<int:pk>/', OrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:pk>/book/', OrderBookView.as_view(), name='order_book'),
    path('my-orders/', MyOrdersView.as_view(), name='my_orders'),

    path('manager/orders/', ManagerOrderListView.as_view(), name='manager_order_list'),
    path('manager/orders/create/', OrderCreateView.as_view(), name='order_create'),
    path('manager/orders/<int:pk>/', ManagerOrderDetailView.as_view(), name='manager_order_detail'),
    path('manager/orders/<int:pk>/confirm/', OrderConfirmBookingView.as_view(), name='order_confirm_booking'),
    path('manager/orders/<int:pk>/reject-booking/', OrderRejectBookingView.as_view(), name='order_reject_booking'),
    path('manager/orders/<int:pk>/revoke-and-block/', OrderRevokeAndBlockView.as_view(), name='order_revoke_and_block'),
    path('manager/orders/<int:pk>/cancel/', OrderCancelView.as_view(), name='order_cancel'),

    path('manager/analytics/', AnalyticsDashboardView.as_view(), name='analytics_dashboard'),
]
