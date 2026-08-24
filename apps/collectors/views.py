import mimetypes

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

from apps.core.mixins import RoleRequiredMixin
from apps.core.models import PersonalDataAccessLog
from apps.payments.models import Rating

from .forms import CHANGE_FIELD_LABELS, CollectorNoteForm, CollectorRegistrationForm, ProfileEditForm
from .models import CollectorNote, CollectorProfile, CollectorProfileChangeRequest, PaymentDetails
from .services import approve_change_request, reject_change_request, submit_profile_change_request

User = get_user_model()


class ManagerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (User.Role.MANAGER, User.Role.ADMIN)


class AdminOnlyRequiredMixin(RoleRequiredMixin):
    """Доступ к паспортным данным — только у ограниченного круга (152-ФЗ, п.2.3 ТЗ)."""

    allowed_roles = (User.Role.ADMIN,)


class CollectorRegisterView(View):
    template_name = 'collectors/register.html'

    def get(self, request):
        return render(request, self.template_name, {'form': CollectorRegistrationForm()})

    def post(self, request):
        form = CollectorRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(request)
            login(request, user)
            messages.success(
                request,
                'Анкета отправлена на проверку. Пока статус не подтверждён, заявки будут недоступны.',
            )
            return redirect('order_list')
        return render(request, self.template_name, {'form': form})


class CollectorProfileDetailView(ManagerRequiredMixin, DetailView):
    """Профиль сборщика для менеджера: фото, ID, рейтинг, история заявок."""

    model = CollectorProfile
    template_name = 'collectors/detail.html'
    context_object_name = 'profile'
    pk_url_kwarg = 'user_id'

    def get_object(self, queryset=None):
        user = get_object_or_404(User, pk=self.kwargs['user_id'])
        return get_object_or_404(CollectorProfile, user=user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ratings = Rating.objects.filter(collector=self.object.user).select_related('order').order_by('-created_at')
        context['ratings'] = ratings
        context['reviews'] = ratings.exclude(comment='')
        # Единый источник правды — CollectorProfile.average_rating/.ratings_count
        # (используются везде: списки заявок, аналитика, уведомления). Не считаем
        # тут заново отдельной агрегацией, чтобы значения не могли разойтись.
        context['average_score'] = self.object.average_rating
        all_orders = self.object.user.booked_orders.order_by('-created_at')
        context['total_orders_count'] = all_orders.count()
        context['orders'] = all_orders[:20]
        context['notes'] = self.object.notes.select_related('author').all()
        context['note_form'] = CollectorNoteForm()
        return context


class CollectorNoteCreateView(ManagerRequiredMixin, View):
    """Внутренняя заметка о сборщике — видна только менеджеру/админу, к заявкам
    не привязана, нужна просто чтобы помнить, кто это такой."""

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        profile = get_object_or_404(CollectorProfile, user=user)
        form = CollectorNoteForm(request.POST)
        if form.is_valid():
            CollectorNote.objects.create(profile=profile, author=request.user, text=form.cleaned_data['text'])
            messages.success(request, 'Заметка добавлена.')
        else:
            messages.error(request, 'Не удалось сохранить заметку — текст не должен быть пустым.')
        return redirect('collector_profile_detail', user_id=user_id)


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class PassportScanView(AdminOnlyRequiredMixin, View):
    """Отдаёт расшифрованный скан паспорта. Каждое обращение логируется (152-ФЗ, п.2.3 ТЗ)."""

    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        profile = get_object_or_404(CollectorProfile, user=user)

        passport = getattr(profile, 'passport', None)
        if not passport or not passport.scan_file:
            return HttpResponseNotFound('Скан паспорта не найден')

        decrypted = passport.scan_file.storage.open_decrypted(passport.scan_file.name)

        PersonalDataAccessLog.objects.create(
            user=request.user,
            target_collector=profile,
            action='viewed_passport_scan',
            ip_address=_client_ip(request),
        )

        content_type, _ = mimetypes.guess_type(passport.scan_file.name)
        response = HttpResponse(decrypted, content_type=content_type or 'application/octet-stream')
        response['Content-Disposition'] = f'inline; filename="passport_{profile.pk}"'
        return response


class MyProfileView(LoginRequiredMixin, View):
    """Сборщик смотрит свои данные и статус ранее поданных заявок на изменение."""

    template_name = 'collectors/my_profile.html'

    def get(self, request):
        profile = get_object_or_404(CollectorProfile, user=request.user)
        pending = profile.change_requests.filter(status=CollectorProfileChangeRequest.Status.PENDING)
        history = profile.change_requests.exclude(status=CollectorProfileChangeRequest.Status.PENDING)[:10]
        return render(request, self.template_name, {
            'profile': profile, 'pending_requests': pending, 'history': history,
            'field_labels': CHANGE_FIELD_LABELS,
        })


class ProfileEditView(LoginRequiredMixin, View):
    template_name = 'collectors/edit_profile.html'

    def _initial(self, profile):
        payment, _ = PaymentDetails.objects.get_or_create(collector=profile)
        return {
            'phone': profile.user.phone, 'email': profile.user.email,
            'region': profile.region_id,
            'specializations': list(profile.specializations.values_list('id', flat=True)),
            'experience_years': profile.experience_years, 'has_own_tools': profile.has_own_tools,
            'tools_list': profile.tools_list, 'has_car': profile.has_car,
            'willing_to_travel': profile.willing_to_travel, 'emergency_contact': profile.emergency_contact,
            'payment_method': payment.method, 'card_or_account_number': payment.card_or_account_number,
            'sbp_phone': payment.sbp_phone, 'cash_pickup_address': payment.cash_pickup_address,
            'cash_pickup_time': payment.cash_pickup_time, 'cash_pickup_contact': payment.cash_pickup_contact,
        }

    def get(self, request):
        profile = get_object_or_404(CollectorProfile, user=request.user)
        form = ProfileEditForm(initial=self._initial(profile), current_user=request.user)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        profile = get_object_or_404(CollectorProfile, user=request.user)
        form = ProfileEditForm(request.POST, current_user=request.user)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        change_request = submit_profile_change_request(profile, form.cleaned_data)
        if change_request:
            messages.success(request, 'Изменения отправлены на подтверждение менеджеру.')
        else:
            messages.info(request, 'Изменений по сравнению с текущими данными не найдено.')
        return redirect('my_profile')


class ChangeRequestListView(ManagerRequiredMixin, ListView):
    """Очередь заявок на изменение анкеты — ждут решения менеджера/админа."""

    model = CollectorProfileChangeRequest
    template_name = 'collectors/change_requests.html'
    context_object_name = 'requests'

    def get_queryset(self):
        return CollectorProfileChangeRequest.objects.filter(
            status=CollectorProfileChangeRequest.Status.PENDING,
        ).select_related('profile', 'profile__user').order_by('created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['field_labels'] = CHANGE_FIELD_LABELS
        return context


class ChangeRequestReviewView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        change_request = get_object_or_404(CollectorProfileChangeRequest, pk=pk)
        if change_request.status != CollectorProfileChangeRequest.Status.PENDING:
            messages.warning(request, 'Эта заявка уже рассмотрена.')
            return redirect('change_requests_list')

        action = request.POST.get('action')
        if action == 'approve':
            approve_change_request(change_request, request.user)
            messages.success(request, 'Изменения применены к анкете сборщика.')
        else:
            reject_change_request(change_request, request.user, reason=request.POST.get('reason', ''))
            messages.info(request, 'Заявка на изменение отклонена.')
        return redirect('change_requests_list')
