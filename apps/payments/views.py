from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import RoleRequiredMixin
from apps.orders.models import Order

from .forms import RatingForm
from .models import PaymentRecord
from .services import mark_payment_paid, rate_collector

User = get_user_model()


class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.MANAGER, User.Role.ADMIN)


class RateCollectorView(ManagerRequiredMixin, View):
    template_name = 'payments/rate.html'

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        initial = {}
        if hasattr(order, 'rating'):
            initial = {
                'score': order.rating.score, 'deadline_met': order.rating.deadline_met,
                'had_complaint': order.rating.had_complaint, 'comment': order.rating.comment,
            }
        form = RatingForm(initial=initial)
        return render(request, self.template_name, {'order': order, 'form': form})

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = RatingForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'order': order, 'form': form})

        try:
            rate_collector(
                order, request.user,
                score=int(form.cleaned_data['score']),
                deadline_met=form.cleaned_data['deadline_met'],
                had_complaint=form.cleaned_data['had_complaint'],
                comment=form.cleaned_data['comment'],
            )
            messages.success(request, 'Оценка сохранена.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('manager_order_detail', pk=pk)


class MarkPaymentPaidView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        record = get_object_or_404(PaymentRecord, order=order)
        mark_payment_paid(record)
        messages.success(request, 'Выплата отмечена как произведённая.')
        return redirect('manager_order_detail', pk=pk)


class PaymentHistoryView(LoginRequiredMixin, ListView):
    """История заявок и сумм у сборщика для его собственного учёта (п.5 ТЗ)."""

    model = PaymentRecord
    template_name = 'payments/history.html'
    context_object_name = 'records'

    def get_queryset(self):
        return PaymentRecord.objects.filter(collector=self.request.user).select_related('order').order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        records = context['records']
        context['total_paid'] = sum((r.amount for r in records if r.is_paid), start=0)
        context['total_pending'] = sum((r.amount for r in records if not r.is_paid), start=0)
        return context
