import calendar as _cal
import json as _json
from collections import defaultdict
from datetime import date as _date
from decimal import Decimal, InvalidOperation
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from .models import Vacation, Day, Expense, VacationSavings
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
        booked = list(
            Vacation.objects.filter(user=user, status=Vacation.STATUS_BOOKED)
            .order_by('start_date')
        )
        review = list(
            Vacation.objects.filter(user=user, status=Vacation.STATUS_REVIEW)
            .order_by(F('start_date').asc(nulls_last=True))
        )
        taken = list(
            Vacation.objects.filter(user=user, status=Vacation.STATUS_TAKEN)
            .order_by('-start_date')
        )
        ctx['booked_vacations'] = booked
        ctx['review_vacations'] = review
        ctx['taken_vacations'] = taken

        ctx['booked_total_budget'] = sum(v.total_budget for v in booked)
        ctx['booked_total_actual'] = sum(v.total_actual for v in booked)
        ctx['booked_remaining'] = ctx['booked_total_budget'] - ctx['booked_total_actual']

        review_budget = sum(v.total_budget for v in review)
        ctx['review_total_budget'] = review_budget
        ctx['review_avg_budget'] = round(review_budget / len(review)) if review else 0

        taken_budget = sum(v.total_budget for v in taken)
        taken_actual = sum(v.total_actual for v in taken)
        ctx['taken_total_budget'] = taken_budget
        ctx['taken_total_actual'] = taken_actual
        ctx['taken_total_variance'] = taken_budget - taken_actual
        ctx['taken_avg_budget'] = round(taken_budget / len(taken)) if taken else 0
        ctx['taken_avg_actual'] = round(taken_actual / len(taken)) if taken else 0

        # Financial overview
        today = _date.today()
        savings_obj, _ = VacationSavings.objects.get_or_create(
            user=user, defaults={'amount': Decimal('0.00')}
        )
        saved_amount = savings_obj.amount

        upcoming = sorted(
            booked + review,
            key=lambda v: (v.start_date is None, v.start_date or _date.max)
        )

        savings_remaining = saved_amount
        financial_rows = []
        for v in upcoming:
            budget_needed = max(Decimal('0.00'), v.total_budget - v.total_actual)
            covered = min(savings_remaining, budget_needed)
            savings_remaining = max(Decimal('0.00'), savings_remaining - covered)
            still_needed = budget_needed - covered

            if v.start_date:
                months = (v.start_date.year - today.year) * 12 + (v.start_date.month - today.month)
                months = max(0, months)
                monthly = (still_needed / months).quantize(Decimal('0.01')) if months > 0 else still_needed
            else:
                months = None
                monthly = None

            pct_covered = int(covered / budget_needed * 100) if budget_needed > 0 else 100
            financial_rows.append({
                'vacation': v,
                'budget_needed': budget_needed,
                'covered': covered,
                'still_needed': still_needed,
                'months_until': months,
                'monthly_needed': monthly,
                'pct_covered': pct_covered,
                'pct_still': 100 - pct_covered,
            })

        total_monthly_needed = sum(
            r['monthly_needed'] for r in financial_rows if r['monthly_needed'] is not None
        )

        ctx['savings_amount'] = saved_amount
        ctx['financial_rows'] = financial_rows
        ctx['total_monthly_needed'] = total_monthly_needed
        ctx['savings_leftover'] = savings_remaining
        ctx['booked_still_needed'] = sum(
            r['still_needed'] for r in financial_rows if r['vacation'].status == Vacation.STATUS_BOOKED
        )
        ctx['review_still_needed'] = sum(
            r['still_needed'] for r in financial_rows if r['vacation'].status == Vacation.STATUS_REVIEW
        )

        # Monthly contribution & balance projection
        monthly_contribution = savings_obj.monthly_contribution
        ctx['monthly_contribution'] = monthly_contribution
        ctx['monthly_contribution_set'] = monthly_contribution is not None

        if monthly_contribution is not None:
            ctx['monthly_difference'] = monthly_contribution - total_monthly_needed

            trip_events = {}
            for v in booked + review:
                if v.start_date:
                    key = (v.start_date.year, v.start_date.month)
                    cost = max(Decimal('0.00'), v.total_budget - v.total_actual)
                    if key not in trip_events:
                        trip_events[key] = {'names': [], 'cost': Decimal('0.00')}
                    trip_events[key]['names'].append(v.name)
                    trip_events[key]['cost'] += cost

            trip_dates = [v.start_date for v in booked + review if v.start_date]
            if trip_dates:
                last_date = max(trip_dates)
                end_year, end_month = last_date.year, last_date.month + 1
                if end_month > 12:
                    end_year, end_month = end_year + 1, 1

                balance = float(saved_amount)
                proj_labels, proj_balances, proj_trip_markers = [], [], []
                cur_year, cur_month, idx = today.year, today.month, 0

                while (cur_year, cur_month) <= (end_year, end_month):
                    if idx > 0:
                        balance += float(monthly_contribution)
                    key = (cur_year, cur_month)
                    if key in trip_events:
                        balance -= float(trip_events[key]['cost'])
                        proj_trip_markers.append({
                            'index': idx,
                            'names': trip_events[key]['names'],
                            'cost': round(float(trip_events[key]['cost']), 2),
                        })
                    proj_labels.append(f"{_cal.month_abbr[cur_month]} {cur_year}")
                    proj_balances.append(round(balance, 2))
                    cur_month += 1
                    if cur_month > 12:
                        cur_year, cur_month = cur_year + 1, 1
                    idx += 1

                ctx['projection_json'] = _json.dumps({
                    'labels': proj_labels,
                    'balances': proj_balances,
                    'trip_markers': proj_trip_markers,
                })
            else:
                ctx['projection_json'] = None
        else:
            ctx['monthly_difference'] = None
            ctx['projection_json'] = None

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
        days = vacation.days.prefetch_related('expenses').all()
        ctx['days'] = days
        ctx['budget_rows'] = vacation.budget_rows()

        by_cat = defaultdict(list)
        for day in days:
            for exp in day.expenses.all():
                by_cat[exp.category].append({
                    'date': day.date.strftime('%b %-d, %Y'),
                    'description': exp.description,
                    'amount': float(exp.amount),
                    'notes': exp.notes,
                })
        ctx['expenses_by_category_json'] = _json.dumps(dict(by_cat))
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


# ── Savings ───────────────────────────────────────────────────────────────────

class UpdateSavingsView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            amount = Decimal(request.POST.get('amount', '0'))
        except InvalidOperation:
            amount = Decimal('0.00')
        try:
            monthly_raw = request.POST.get('monthly_contribution', '').strip()
            monthly = Decimal(monthly_raw) if monthly_raw else None
            if monthly is not None:
                monthly = max(Decimal('0.00'), monthly)
        except InvalidOperation:
            monthly = None
        obj, _ = VacationSavings.objects.get_or_create(user=request.user)
        obj.amount = max(Decimal('0.00'), amount)
        obj.monthly_contribution = monthly
        obj.save()
        return redirect(reverse('dashboard'))


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
