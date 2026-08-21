from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, View

from apps.collectors.models import CollectorProfile
from apps.collectors.services import block_collector
from apps.core.mixins import RoleRequiredMixin

from .forms import OrderCreateForm
from .models import Order
from .services import (
    OrderBookingError,
    book_order,
    cancel_order,
    confirm_booking,
    reject_booking,
    revoke_booking,
)

User = get_user_model()


class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.MANAGER, User.Role.ADMIN)


class CollectorConfirmedRequiredMixin(LoginRequiredMixin):
    """Без подтверждённой анкеты сборщик не видит заявки (п.2.2 ТЗ)."""

    def get(self, request, *args, **kwargs):
        if request.user.role != User.Role.COLLECTOR:
            return redirect('manager_order_list')
        if not self._is_confirmed_collector(request.user):
            messages.warning(request, 'Заявки доступны только сборщикам с подтверждённой анкетой.')
            return redirect('my_orders')
        return super().get(request, *args, **kwargs)

    @staticmethod
    def _is_confirmed_collector(user):
        profile = getattr(user, 'collector_profile', None)
        return profile is not None and profile.status == CollectorProfile.Status.CONFIRMED


class OrderListView(CollectorConfirmedRequiredMixin, ListView):
    model = Order
    template_name = 'orders/list.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return Order.objects.filter(status=Order.Status.PUBLISHED).order_by('deadline_at')


class OrderDetailView(LoginRequiredMixin, DetailView):
    """Карточка заявки для сборщика. Менеджеров сюда не пускаем — у них своя (см. ManagerOrderDetailView)."""

    model = Order
    template_name = 'orders/detail.html'
    context_object_name = 'order'

    def get(self, request, *args, **kwargs):
        if request.user.role != User.Role.COLLECTOR:
            return redirect('manager_order_detail', pk=kwargs['pk'])
        return super().get(request, *args, **kwargs)


class OrderBookView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            book_order(pk, request.user)
            messages.success(request, 'Заявка забронирована. Ожидайте подтверждения администратором.')
        except OrderBookingError as exc:
            messages.error(request, str(exc))
        return redirect('order_detail', pk=pk)


class MyOrdersView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'orders/my_orders.html'
    context_object_name = 'orders'

    def get_queryset(self):
        return Order.objects.filter(collector=self.request.user).order_by('-created_at')


class OrderCreateView(ManagerRequiredMixin, CreateView):
    model = Order
    form_class = OrderCreateForm
    template_name = 'orders/create.html'
    success_url = reverse_lazy('manager_order_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.status = Order.Status.PUBLISHED
        messages.success(self.request, 'Заявка создана и опубликована.')
        return super().form_valid(form)


class ManagerOrderListView(ManagerRequiredMixin, ListView):
    model = Order
    template_name = 'orders/manager_list.html'
    context_object_name = 'orders'
    paginate_by = 25

    STATUS_FILTERS = {
        'active': [
            Order.Status.PUBLISHED, Order.Status.BOOKED, Order.Status.CONFIRMED,
            Order.Status.IN_PROGRESS, Order.Status.REPORT_UPLOADED, Order.Status.REJECTED_FOR_REWORK,
            Order.Status.ACCEPTED,
        ],
        'closed': [Order.Status.CLOSED, Order.Status.CANCELLED],
    }

    def get_queryset(self):
        qs = Order.objects.select_related(
            'furniture_type', 'collector', 'collector__collector_profile',
        ).order_by('deadline_at')

        status = self.request.GET.get('status')
        if status in dict(Order.Status.choices):
            qs = qs.filter(status=status)
        elif self.request.GET.get('view') == 'closed':
            qs = qs.filter(status__in=self.STATUS_FILTERS['closed'])
        else:
            qs = qs.filter(status__in=self.STATUS_FILTERS['active'])

        search = self.request.GET.get('q')
        if search:
            qs = qs.filter(address__icontains=search)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        base_qs = Order.objects.filter(status__in=self.STATUS_FILTERS['active'])
        context['awaiting_confirmation_count'] = base_qs.filter(status=Order.Status.BOOKED).count()
        context['report_review_count'] = base_qs.filter(status=Order.Status.REPORT_UPLOADED).count()
        context['overdue_count'] = base_qs.filter(deadline_at__lt=now).count()
        context['current_status'] = self.request.GET.get('status', '')
        context['current_view'] = self.request.GET.get('view', 'active')
        context['search_query'] = self.request.GET.get('q', '')
        context['status_choices'] = Order.Status.choices
        return context


class ManagerOrderDetailView(ManagerRequiredMixin, DetailView):
    model = Order
    template_name = 'orders/manager_detail.html'
    context_object_name = 'order'


class OrderConfirmBookingView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        try:
            confirm_booking(pk, request.user)
            messages.success(request, 'Бронь подтверждена.')
        except OrderBookingError as exc:
            messages.error(request, str(exc))
        return redirect(request.POST.get('next', 'manager_order_list'))


class OrderRejectBookingView(ManagerRequiredMixin, View):
    """Админ не подтверждает бронь (сомнения по сборщику) — без блокировки сборщика."""

    def post(self, request, pk):
        reject_booking(pk, request.user, reason=request.POST.get('reason', ''))
        messages.success(request, 'Бронь отклонена, заявка возвращена в пул.')
        return redirect(request.POST.get('next', 'manager_order_list'))


class OrderRevokeAndBlockView(ManagerRequiredMixin, View):
    """Сборщик пропал: снять бронь и заблокировать сборщика одним действием (п.3.2 ТЗ)."""

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        collector_user = order.collector
        reason = request.POST.get('reason', 'Сборщик пропал: не вышел на связь / не сдал работу в срок')

        revoke_booking(pk, request.user, reason=reason)

        if collector_user is not None:
            profile = getattr(collector_user, 'collector_profile', None)
            if profile:
                block_collector(profile, reason=reason)
                messages.success(request, f'Бронь снята, сборщик {collector_user} заблокирован.')
            else:
                messages.warning(request, 'Бронь снята, но у сборщика нет анкеты для блокировки.')
        else:
            messages.success(request, 'Бронь снята.')

        return redirect(request.POST.get('next', 'manager_order_list'))


class OrderCancelView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        cancel_order(pk, request.user, reason=request.POST.get('reason', ''))
        messages.success(request, 'Заявка отменена.')
        return redirect(request.POST.get('next', 'manager_order_list'))
