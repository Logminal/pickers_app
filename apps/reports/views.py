from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.core.mixins import RoleRequiredMixin
from apps.orders.models import Order

from .forms import ADDITIONAL_WORK_ROWS, DEFAULT_CHECKLIST, ActUploadForm, SlotPhotoForm
from .models import Act
from .services import close_order, review_photo_report, submit_photo_report

User = get_user_model()


class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.MANAGER, User.Role.ADMIN)


def _parse_additional_works(post_data):
    """Строки 'extra_work_desc_N' / 'extra_work_price_N' — фиксированное число необязательных строк."""
    works = []
    for i in range(1, ADDITIONAL_WORK_ROWS + 1):
        description = post_data.get(f'extra_work_desc_{i}', '').strip()
        price_raw = post_data.get(f'extra_work_price_{i}', '').strip()
        if not description or not price_raw:
            continue
        try:
            price = Decimal(price_raw.replace(',', '.'))
        except InvalidOperation:
            continue
        works.append({'description': description, 'price': price})
    return works


class PhotoReportUploadView(LoginRequiredMixin, View):
    template_name = 'reports/upload.html'

    def _get_order(self, request, pk):
        return get_object_or_404(Order, pk=pk, collector=request.user)

    def _get_slots(self, order):
        template = order.furniture_type.photo_slots_template
        return template.slots.all() if template else []

    def get(self, request, pk):
        order = self._get_order(request, pk)
        slots = self._get_slots(order)
        form = SlotPhotoForm(slots=slots)
        return render(request, self.template_name, {
            'order': order, 'form': form, 'checklist': DEFAULT_CHECKLIST,
            'additional_work_rows': range(1, ADDITIONAL_WORK_ROWS + 1),
        })

    def post(self, request, pk):
        order = self._get_order(request, pk)
        slots = self._get_slots(order)
        form = SlotPhotoForm(slots=slots, data=request.POST, files=request.FILES)

        if not form.is_valid():
            return render(request, self.template_name, {
                'order': order, 'form': form, 'checklist': DEFAULT_CHECKLIST,
                'additional_work_rows': range(1, ADDITIONAL_WORK_ROWS + 1),
            })

        slot_files = {}
        for slot in slots:
            field_name = f'slot_{slot.id}'
            if field_name in request.FILES:
                slot_files[slot.id] = request.FILES[field_name]

        checked_items = request.POST.getlist('checklist')
        additional_works = _parse_additional_works(request.POST)
        submit_photo_report(
            order=order, collector=request.user, slot_files=slot_files,
            checked_items=checked_items, comment=request.POST.get('comment', ''),
            additional_works=additional_works,
        )
        messages.success(request, 'Фотоотчёт отправлен менеджеру на проверку.')
        return redirect('order_detail', pk=order.pk)


class PhotoReportReviewView(ManagerRequiredMixin, View):
    template_name = 'reports/review.html'

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        return render(request, self.template_name, {
            'order': order, 'report': order.photo_report, 'act_form': ActUploadForm(),
        })

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        action = request.POST.get('action')
        if action == 'accept':
            review_photo_report(order, request.user, accepted=True)
            messages.success(request, 'Фотоотчёт принят.')
        else:
            review_photo_report(order, request.user, accepted=False, comment=request.POST.get('comment', ''))
            messages.info(request, 'Фотоотчёт отклонён, отправлен сборщику на доработку.')
        return redirect('manager_order_detail', pk=pk)


class ActUploadView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = ActUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, 'Прикрепите файл акта и подтвердите его читаемость.')
            return redirect('report_review', pk=pk)

        Act.objects.update_or_create(
            order=order,
            defaults={
                'file': form.cleaned_data['act_file'],
                'uploaded_by': request.user,
                'is_readable_confirmed': form.cleaned_data['is_readable_confirmed'],
            },
        )
        messages.success(request, 'Акт прикреплён. Теперь можно закрыть заявку.')
        return redirect('report_review', pk=pk)


class OrderCloseView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        try:
            close_order(order, request.user)
            messages.success(request, 'Заявка закрыта.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('manager_order_detail', pk=pk)
