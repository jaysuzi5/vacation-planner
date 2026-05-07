import json as _json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from .models import Vacation, Day, Expense
from .forms import VacationForm, DayForm, ExpenseForm


class OwnerRequiredMixin:
    """Enforce that the vacation (or day/expense's vacation) belongs to request.user."""

    def get_vacation(self):
        raise NotImplementedError

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        vacation = self.get_vacation()
        if vacation and vacation.user != request.user:
            raise PermissionDenied
        return response


class DashboardView(LoginRequiredMixin, ListView):
    model = Vacation
    template_name = 'planner/dashboard.html'
    context_object_name = 'vacations'

    def get_queryset(self):
        return Vacation.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        ctx['booked_vacations'] = (
            Vacation.objects.filter(user=user, status=Vacation.STATUS_BOOKED)
            .order_by('start_date')
        )
        ctx['review_vacations'] = (
            Vacation.objects.filter(user=user, status=Vacation.STATUS_REVIEW)
            .order_by(F('rating').desc(nulls_last=True), 'name')
        )
        ctx['taken_vacations'] = (
            Vacation.objects.filter(user=user, status=Vacation.STATUS_TAKEN)
            .order_by('-start_date')
        )
        return ctx


class VacationDetailView(LoginRequiredMixin, DetailView):
    model = Vacation
    template_name = 'planner/vacation_detail.html'
    context_object_name = 'vacation'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.user != self.request.user:
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        vacation = self.object
        ctx['days'] = vacation.days.prefetch_related('expenses').all()
        ctx['budget_rows'] = vacation.budget_rows()
        return ctx


class VacationCreateView(LoginRequiredMixin, CreateView):
    model = Vacation
    form_class = VacationForm
    template_name = 'planner/vacation_form.html'

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'New Vacation'
        ctx['submit_label'] = 'Create Vacation'
        return ctx


class VacationEditView(LoginRequiredMixin, UpdateView):
    model = Vacation
    form_class = VacationForm
    template_name = 'planner/vacation_form.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.user != self.request.user:
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = f'Edit — {self.object.name}'
        ctx['submit_label'] = 'Save Changes'
        return ctx


class VacationDeleteView(LoginRequiredMixin, DeleteView):
    model = Vacation
    template_name = 'planner/confirm_delete.html'
    success_url = reverse_lazy('dashboard')

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.user != self.request.user:
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['item_name'] = str(self.object)
        ctx['cancel_url'] = self.object.get_absolute_url()
        return ctx


# ── Day views ────────────────────────────────────────────────────────────────

class DayCreateView(LoginRequiredMixin, CreateView):
    model = Day
    form_class = DayForm
    template_name = 'planner/day_form.html'

    def _get_vacation(self):
        if not hasattr(self, '_vacation'):
            self._vacation = Vacation.objects.get(pk=self.kwargs['vacation_pk'])
            if self._vacation.user != self.request.user:
                raise PermissionDenied
        return self._vacation

    def form_valid(self, form):
        form.instance.vacation = self._get_vacation()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vacation'] = self._get_vacation()
        ctx['form_title'] = 'Add Day'
        ctx['submit_label'] = 'Add Day'
        return ctx


class DayEditView(LoginRequiredMixin, UpdateView):
    model = Day
    form_class = DayForm
    template_name = 'planner/day_form.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.vacation.user != self.request.user:
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['vacation'] = self.object.vacation
        ctx['form_title'] = f'Edit Day — {self.object.date}'
        ctx['submit_label'] = 'Save Day'
        return ctx


class DayDeleteView(LoginRequiredMixin, DeleteView):
    model = Day
    template_name = 'planner/confirm_delete.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.vacation.user != self.request.user:
            raise PermissionDenied
        return obj

    def get_success_url(self):
        return self.object.vacation.get_absolute_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['item_name'] = f'Day — {self.object.date}'
        ctx['cancel_url'] = self.object.vacation.get_absolute_url()
        return ctx


# ── Expense views ─────────────────────────────────────────────────────────────

class ExpenseCreateView(LoginRequiredMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'planner/expense_form.html'

    def _get_day(self):
        if not hasattr(self, '_day'):
            self._day = Day.objects.select_related('vacation').get(pk=self.kwargs['day_pk'])
            if self._day.vacation.user != self.request.user:
                raise PermissionDenied
        return self._day

    def form_valid(self, form):
        form.instance.day = self._get_day()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['day'] = self._get_day()
        ctx['form_title'] = f'Add Expense — {self._get_day().date}'
        ctx['submit_label'] = 'Add Expense'
        return ctx


class ExpenseEditView(LoginRequiredMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'planner/expense_form.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.day.vacation.user != self.request.user:
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['day'] = self.object.day
        ctx['form_title'] = f'Edit Expense — {self.object.description}'
        ctx['submit_label'] = 'Save Expense'
        return ctx


class ExpenseDeleteView(LoginRequiredMixin, DeleteView):
    model = Expense
    template_name = 'planner/confirm_delete.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.day.vacation.user != self.request.user:
            raise PermissionDenied
        return obj

    def get_success_url(self):
        return self.object.day.vacation.get_absolute_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['item_name'] = f'Expense — {self.object.description}'
        ctx['cancel_url'] = self.object.day.vacation.get_absolute_url()
        return ctx


# ── Offline / PWA API ─────────────────────────────────────────────────────────

class ExpenseCreateApiView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            data = _json.loads(request.body)
            day = Day.objects.select_related('vacation').get(pk=int(data['day_pk']))
            if day.vacation.user != request.user:
                return JsonResponse({'error': 'forbidden'}, status=403)
            form = ExpenseForm({
                'description': data.get('description', ''),
                'category': data.get('category', ''),
                'amount': data.get('amount', ''),
            })
            if form.is_valid():
                expense = form.save(commit=False)
                expense.day = day
                expense.save()
                return JsonResponse({'id': expense.pk, 'status': 'ok'})
            return JsonResponse({'errors': form.errors}, status=400)
        except (KeyError, ValueError, Day.DoesNotExist) as e:
            return JsonResponse({'error': str(e)}, status=400)
