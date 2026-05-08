from decimal import Decimal
from functools import cached_property
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Sum
from django.urls import reverse


class Vacation(models.Model):
    STATUS_REVIEW = 'review'
    STATUS_BOOKED = 'booked'
    STATUS_TAKEN = 'taken'
    STATUS_CHOICES = [
        (STATUS_REVIEW, 'In Review'),
        (STATUS_BOOKED, 'Booked'),
        (STATUS_TAKEN, 'Taken'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vacations')
    shared_with = models.ManyToManyField(User, blank=True, related_name='shared_vacations')
    name = models.CharField(max_length=200)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_REVIEW)
    notes = models.TextField(blank=True)

    # Budget
    airfare_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    lodging_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    meals_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    excursions_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    gas_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    cruise_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    car_rental_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    misc_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Actual (legacy columns — actuals now computed from logged Expense records)
    airfare_actual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    lodging_actual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    meals_actual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    excursions_actual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    gas_actual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    cruise_actual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    car_rental_actual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    misc_actual = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', '-created_at']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('vacation_detail', kwargs={'pk': self.pk})

    def can_access(self, user):
        return user == self.user or self.shared_with.filter(pk=user.pk).exists()

    @cached_property
    def expense_totals(self):
        """Single query: expense amounts grouped by category for this vacation."""
        totals = {cat: Decimal('0.00') for cat, _ in Expense.CATEGORY_CHOICES}
        qs = Expense.objects.filter(day__vacation=self).values('category').annotate(total=Sum('amount'))
        for row in qs:
            if row['category'] in totals:
                totals[row['category']] = row['total']
        return totals

    @property
    def total_budget(self):
        return (self.airfare_budget + self.lodging_budget + self.meals_budget +
                self.excursions_budget + self.gas_budget + self.misc_budget +
                self.cruise_budget + self.car_rental_budget)

    @property
    def total_actual(self):
        return sum(self.expense_totals.values())

    @property
    def variance(self):
        return self.total_budget - self.total_actual

    @property
    def status_badge_class(self):
        return {
            self.STATUS_REVIEW: 'bg-warning text-dark',
            self.STATUS_BOOKED: 'bg-primary',
            self.STATUS_TAKEN: 'bg-success',
        }.get(self.status, 'bg-secondary')

    @property
    def duration_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    def budget_rows(self):
        totals = self.expense_totals
        categories = [
            ('airfare',    'Airfare',    self.airfare_budget,    totals['airfare'],    'bi-airplane'),
            ('lodging',    'Lodging',    self.lodging_budget,    totals['lodging'],    'bi-house'),
            ('meals',      'Meals',      self.meals_budget,      totals['meals'],      'bi-cup-hot'),
            ('excursions', 'Excursions', self.excursions_budget, totals['excursions'], 'bi-map'),
            ('gas',        'Gas',        self.gas_budget,        totals['gas'],        'bi-fuel-pump'),
            ('cruise',     'Cruise',     self.cruise_budget,     totals['cruise'],     'bi-compass'),
            ('car_rental', 'Car Rental', self.car_rental_budget, totals['car_rental'], 'bi-car-front'),
            ('misc',       'Misc.',      self.misc_budget,       totals['misc'],       'bi-bag'),
        ]
        return [
            {
                'key': key,
                'label': label,
                'budget': budget,
                'actual': actual,
                'variance': budget - actual,
                'icon': icon,
            }
            for key, label, budget, actual, icon in categories
        ]


class Day(models.Model):
    vacation = models.ForeignKey(Vacation, on_delete=models.CASCADE, related_name='days')
    date = models.DateField()
    lodging = models.CharField(max_length=200, blank=True)
    excursion = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['date']
        unique_together = ['vacation', 'date']

    def __str__(self):
        return f"{self.vacation.name} — {self.date}"

    def get_absolute_url(self):
        return reverse('vacation_detail', kwargs={'pk': self.vacation.pk})

    def day_total(self):
        return self.expenses.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')


class Expense(models.Model):
    CATEGORY_AIRFARE = 'airfare'
    CATEGORY_LODGING = 'lodging'
    CATEGORY_MEALS = 'meals'
    CATEGORY_EXCURSIONS = 'excursions'
    CATEGORY_GAS = 'gas'
    CATEGORY_CRUISE = 'cruise'
    CATEGORY_CAR_RENTAL = 'car_rental'
    CATEGORY_MISC = 'misc'
    CATEGORY_CHOICES = [
        (CATEGORY_AIRFARE, 'Airfare'),
        (CATEGORY_LODGING, 'Lodging'),
        (CATEGORY_MEALS, 'Meals'),
        (CATEGORY_EXCURSIONS, 'Excursions'),
        (CATEGORY_GAS, 'Gas'),
        (CATEGORY_CRUISE, 'Cruise'),
        (CATEGORY_CAR_RENTAL, 'Car Rental'),
        (CATEGORY_MISC, 'Miscellaneous'),
    ]

    day = models.ForeignKey(Day, on_delete=models.CASCADE, related_name='expenses')
    description = models.CharField(max_length=300)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['category', 'description']

    def __str__(self):
        return f"{self.description} — ${self.amount}"



    def get_absolute_url(self):
        return reverse('vacation_detail', kwargs={'pk': self.day.vacation.pk})


class VacationSavings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vacation_savings')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    monthly_contribution = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} — ${self.amount}"
