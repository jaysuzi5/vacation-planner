import calendar as _cal
import json as _json
from collections import defaultdict
from datetime import date as _date
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from .models import Vacation, Day, Expense, JournalEntry, DayPhoto, VacationSavings, FamilyLink
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
        user = self.request.user
        family_pks = list(FamilyLink.objects.filter(user=user).values_list('member', flat=True))
        q = Q(user=user) | Q(shared_with=user)
        if family_pks:
            q |= Q(user__in=family_pks)
        return Vacation.objects.filter(q).distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # Family members — computed once, reused for trip queryset and savings
        family_pks = list(FamilyLink.objects.filter(user=user).values_list('member', flat=True))
        ctx['family_members'] = list(User.objects.filter(pk__in=family_pks)) if family_pks else []

        base = Q(user=user) | Q(shared_with=user)
        if family_pks:
            base |= Q(user__in=family_pks)
        booked = list(
            Vacation.objects.filter(base, status=Vacation.STATUS_BOOKED)
            .distinct().order_by('start_date')
        )
        review = list(
            Vacation.objects.filter(base, status=Vacation.STATUS_REVIEW)
            .distinct().order_by(F('start_date').asc(nulls_last=True))
        )
        taken = list(
            Vacation.objects.filter(base, status=Vacation.STATUS_TAKEN)
            .distinct().order_by('-start_date')
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

        # Pool savings across family members
        family_savings_qs = (
            VacationSavings.objects.filter(user__in=family_pks).select_related('user')
            if family_pks else VacationSavings.objects.none()
        )
        family_savings_list = list(family_savings_qs)
        ctx['family_savings_breakdown'] = [(s.user, s.amount, s.monthly_contribution) for s in family_savings_list]
        saved_amount = savings_obj.amount + sum(s.amount for s in family_savings_list)

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
                # proj_covered/shortage/pct_proj/pct_shortage filled in below
                'proj_covered': Decimal('0'),
                'shortage': still_needed,
                'pct_proj': 0,
                'pct_shortage': 100 - pct_covered,
            })

        # Correct formula: minimum monthly M so the running balance never goes negative.
        # For each trip i (ordered by date): M >= max(0, (cumulative_cost_i - saved_amount) / months_i)
        cumulative_needed = Decimal('0')
        total_monthly_needed = Decimal('0')
        for row in financial_rows:
            if row['months_until'] is not None and row['months_until'] > 0:
                cumulative_needed += row['budget_needed']
                required = max(Decimal('0'), (cumulative_needed - saved_amount) / row['months_until'])
                if required > total_monthly_needed:
                    total_monthly_needed = required
        total_monthly_needed = total_monthly_needed.quantize(Decimal('0.01'))

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

        # Monthly contribution — pool own + family
        ctx['my_savings_amount'] = savings_obj.amount
        ctx['my_monthly_contribution'] = savings_obj.monthly_contribution
        ctx['my_monthly_contribution_set'] = savings_obj.monthly_contribution is not None

        all_monthly = [savings_obj.monthly_contribution] + [s.monthly_contribution for s in family_savings_list]
        set_monthly = [m for m in all_monthly if m is not None]
        monthly_contribution = sum(set_monthly) if set_monthly else None
        ctx['monthly_contribution'] = monthly_contribution
        ctx['monthly_contribution_set'] = monthly_contribution is not None

        if monthly_contribution is not None:
            diff = monthly_contribution - total_monthly_needed
            diff_int = round(float(diff))
            ctx['monthly_difference'] = diff
            ctx['monthly_difference_int'] = diff_int
            ctx['monthly_difference_abs'] = abs(diff_int)

            # Per-row three-way coverage: green (saved), blue (projected), red (shortage)
            actual_pool_f = float(saved_amount)
            proj_pool_f = float(saved_amount)
            prev_mo = 0
            for row in financial_rows:
                budget_f = float(row['budget_needed'])
                mo = row['months_until']
                if mo is not None and mo > prev_mo:
                    proj_pool_f += float(monthly_contribution) * (mo - prev_mo)
                    prev_mo = mo
                green_f = min(actual_pool_f, budget_f)
                actual_pool_f = max(0.0, actual_pool_f - green_f)
                proj_cover_f = min(proj_pool_f, budget_f)
                blue_f = max(0.0, proj_cover_f - green_f)
                red_f = max(0.0, budget_f - green_f - blue_f)
                proj_pool_f = max(0.0, proj_pool_f - budget_f)
                row['proj_covered'] = Decimal(str(round(blue_f, 2)))
                row['shortage'] = Decimal(str(round(red_f, 2)))
                if budget_f > 0:
                    row['pct_proj'] = round(blue_f / budget_f * 100)
                    row['pct_shortage'] = 100 - row['pct_covered'] - row['pct_proj']
                else:
                    row['pct_proj'] = 0
                    row['pct_shortage'] = 0

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
        if not obj.can_access(self.request.user):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        vacation = self.object
        days = vacation.days.prefetch_related('expenses').all()
        ctx['days'] = days
        ctx['budget_rows'] = vacation.budget_rows()
        ctx['shared_users'] = list(vacation.shared_with.all())
        ctx['is_owner'] = vacation.user == self.request.user

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
        if not obj.can_access(self.request.user):
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
            if not self._vacation.can_access(self.request.user):
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
        if not obj.vacation.can_access(self.request.user):
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
        if not obj.vacation.can_access(self.request.user):
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
            if not self._day.vacation.can_access(self.request.user):
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
        if not obj.day.vacation.can_access(self.request.user):
            raise PermissionDenied
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['day'] = self.object.day
        ctx['form_title'] = f'Edit Expense — {self.object.description}'
        ctx['submit_label'] = 'Save Expense'
        ctx['expense_pk'] = self.object.pk
        return ctx


class ExpenseDeleteView(LoginRequiredMixin, DeleteView):
    model = Expense
    template_name = 'planner/confirm_delete.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not obj.day.vacation.can_access(self.request.user):
            raise PermissionDenied
        return obj

    def get_success_url(self):
        return self.object.day.vacation.get_absolute_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['item_name'] = f'Expense — {self.object.description}'
        ctx['cancel_url'] = self.object.day.vacation.get_absolute_url()
        return ctx


# ── Sharing ───────────────────────────────────────────────────────────────────

class ShareVacationView(LoginRequiredMixin, View):
    def post(self, request, pk):
        vacation = get_object_or_404(Vacation, pk=pk, user=request.user)
        action = request.POST.get('action')
        if action == 'add':
            email = request.POST.get('email', '').strip()
            try:
                target = User.objects.get(email__iexact=email)
                if target == request.user:
                    messages.warning(request, "Can't share a trip with yourself.")
                else:
                    vacation.shared_with.add(target)
            except User.DoesNotExist:
                messages.error(request, f"No account found for {email}.")
        elif action == 'remove':
            user_id = request.POST.get('user_id')
            vacation.shared_with.remove(user_id)
        return redirect(vacation.get_absolute_url())


# ── Family ────────────────────────────────────────────────────────────────────

class FamilySettingsView(LoginRequiredMixin, View):
    def post(self, request):
        action = request.POST.get('action')
        if action == 'add':
            email = request.POST.get('email', '').strip()
            try:
                target = User.objects.get(email__iexact=email)
                if target == request.user:
                    messages.warning(request, "Can't add yourself as a family member.")
                elif FamilyLink.objects.filter(user=request.user, member=target).exists():
                    messages.info(request, f"{target.email} is already a family member.")
                else:
                    FamilyLink.objects.create(user=request.user, member=target)
                    FamilyLink.objects.get_or_create(user=target, member=request.user)
                    messages.success(request, f"Added {target.email} as a family member.")
            except User.DoesNotExist:
                messages.error(request, f"No account found for {email}.")
        elif action == 'remove':
            member_id = request.POST.get('member_id')
            FamilyLink.objects.filter(user=request.user, member_id=member_id).delete()
            FamilyLink.objects.filter(user_id=member_id, member=request.user).delete()
        return redirect(reverse('dashboard'))


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
            if not day.vacation.can_access(request.user):
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


# ── Journal & Photos ──────────────────────────────────────────────────────────

class JournalEntryApiView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            data = _json.loads(request.body)
            day = Day.objects.select_related('vacation').get(pk=int(data['day_pk']))
            if not day.vacation.can_access(request.user):
                return JsonResponse({'error': 'forbidden'}, status=403)
            text = data.get('text', '').strip()
            if not text:
                return JsonResponse({'error': 'text required'}, status=400)
            entry = JournalEntry.objects.create(day=day, text=text)
            return JsonResponse({'id': entry.pk, 'status': 'ok'})
        except (KeyError, ValueError, Day.DoesNotExist) as e:
            return JsonResponse({'error': str(e)}, status=400)


class DayJournalView(LoginRequiredMixin, View):
    def _get_day(self, request, pk):
        day = get_object_or_404(Day.objects.select_related('vacation'), pk=pk)
        if not day.vacation.can_access(request.user):
            raise PermissionDenied
        return day

    def get(self, request, pk):
        day = self._get_day(request, pk)
        return render(request, 'planner/day_journal.html', {
            'day': day,
            'vacation': day.vacation,
            'journal_entries': day.journal_entries.all(),
            'photos': day.photos.all(),
            'is_owner': day.vacation.user == request.user,
        })

    def post(self, request, pk):
        day = self._get_day(request, pk)
        action = request.POST.get('action')
        if action == 'journal':
            text = request.POST.get('text', '').strip()
            if text:
                JournalEntry.objects.create(day=day, text=text)
                messages.success(request, 'Entry added.')
            else:
                messages.warning(request, 'Entry cannot be blank.')
        elif action == 'upload':
            img = request.FILES.get('image')
            if img:
                DayPhoto.objects.create(
                    day=day,
                    image=img,
                    caption=request.POST.get('caption', ''),
                )
                messages.success(request, 'Photo added.')
            else:
                messages.warning(request, 'No file selected.')
        return redirect('day_journal', pk=day.pk)


class DayPhotoDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        photo = get_object_or_404(DayPhoto.objects.select_related('day__vacation'), pk=pk)
        if not photo.day.vacation.can_access(request.user):
            raise PermissionDenied
        day_pk = photo.day.pk
        photo.image.delete(save=False)
        photo.delete()
        messages.success(request, 'Photo deleted.')
        return redirect('day_journal', pk=day_pk)


class JournalEntryDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry.objects.select_related('day__vacation'), pk=pk)
        if not entry.day.vacation.can_access(request.user):
            raise PermissionDenied
        day_pk = entry.day.pk
        entry.delete()
        messages.success(request, 'Entry deleted.')
        return redirect('day_journal', pk=day_pk)


class VacationRecapView(LoginRequiredMixin, View):
    def get(self, request, pk):
        vacation = get_object_or_404(Vacation, pk=pk)
        if not vacation.can_access(request.user):
            raise PermissionDenied
        days = vacation.days.prefetch_related(
            'expenses', 'journal_entries', 'photos'
        ).all()
        return render(request, 'planner/vacation_recap.html', {
            'vacation': vacation,
            'days': days,
            'budget_rows': vacation.budget_rows(),
        })
