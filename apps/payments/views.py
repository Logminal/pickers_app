from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import RoleRequiredMixin
from apps.orders.models import Order

from .forms import RatingForm, WithdrawalReceiptForm, WithdrawalRequestForm
from .models import PaymentRecord, WithdrawalRequest
from .services import (
    WithdrawalRequestError,
    cancel_withdrawal_request,
    complete_withdrawal_request,
    create_withdrawal_request,
    mark_payment_paid,
    rate_collector,
)

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
        context['pending_withdrawal'] = WithdrawalRequest.objects.filter(
            collector=self.request.user, status=WithdrawalRequest.Status.PENDING,
        ).first()
        context['withdrawal_history'] = WithdrawalRequest.objects.filter(
            collector=self.request.user,
        ).exclude(status=WithdrawalRequest.Status.PENDING)[:10]
        return context


class WithdrawalRequestCreateView(LoginRequiredMixin, View):
    template_name = 'payments/withdraw.html'

    def get(self, request):
        total_pending = sum(
            (r.amount for r in PaymentRecord.objects.filter(collector=request.user, is_paid=False)), start=0,
        )
        form = WithdrawalRequestForm()
        return render(request, self.template_name, {'form': form, 'total_pending': total_pending})

    def post(self, request):
        form = WithdrawalRequestForm(request.POST)
        if not form.is_valid():
            total_pending = sum(
                (r.amount for r in PaymentRecord.objects.filter(collector=request.user, is_paid=False)), start=0,
            )
            return render(request, self.template_name, {'form': form, 'total_pending': total_pending})

        try:
            create_withdrawal_request(
                request.user, method=form.cleaned_data['method'],
                requisite=form.cleaned_data['requisite'], comment=form.cleaned_data['comment'],
            )
            messages.success(request, 'Заявка на выплату отправлена. Ожидайте звонка.')
        except WithdrawalRequestError as exc:
            messages.error(request, str(exc))
        return redirect('payment_history')


class WithdrawalRequestListView(ManagerRequiredMixin, ListView):
    """Очередь заявок на выплату — менеджер видит, кому звонить."""

    model = WithdrawalRequest
    template_name = 'payments/withdrawal_requests.html'
    context_object_name = 'requests'

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(
            status=WithdrawalRequest.Status.PENDING,
        ).select_related('collector', 'collector__collector_profile').order_by('created_at')


class WithdrawalRequestCompleteView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        request_obj = get_object_or_404(WithdrawalRequest, pk=pk)
        action = request.POST.get('action')
        try:
            if action == 'complete':
                receipt_form = WithdrawalReceiptForm(request.POST, request.FILES)
                if not receipt_form.is_valid():
                    messages.error(request, 'Не удалось прикрепить чек — проверьте файл (jpg/png/pdf, до 8 МБ).')
                    return redirect('withdrawal_requests_list')
                complete_withdrawal_request(
                    request_obj, request.user, receipt=receipt_form.cleaned_data.get('receipt'),
                )
                messages.success(request, 'Выплата отмечена как произведённая.')
            else:
                cancel_withdrawal_request(request_obj, request.user, reason=request.POST.get('reason', ''))
                messages.info(request, 'Заявка на выплату отменена.')
        except WithdrawalRequestError as exc:
            messages.error(request, str(exc))
        return redirect('withdrawal_requests_list')
