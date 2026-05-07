from django.contrib import admin
from .models import Vacation, Day, Expense


class ExpenseInline(admin.TabularInline):
    model = Expense
    extra = 1


class DayInline(admin.StackedInline):
    model = Day
    extra = 0
    show_change_link = True


@admin.register(Vacation)
class VacationAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'user', 'status', 'start_date', 'end_date', 'total_budget', 'total_actual']
    list_filter = ['status', 'user']
    search_fields = ['name', 'location', 'user__email']
    inlines = [DayInline]
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Day)
class DayAdmin(admin.ModelAdmin):
    list_display = ['date', 'vacation', 'lodging', 'excursion']
    list_filter = ['vacation__user']
    search_fields = ['vacation__name', 'lodging', 'excursion']
    inlines = [ExpenseInline]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['description', 'category', 'amount', 'day']
    list_filter = ['category', 'day__vacation__user']
    search_fields = ['description', 'day__vacation__name']
