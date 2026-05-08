from django import forms
from .models import Vacation, Day, Expense


class VacationForm(forms.ModelForm):
    class Meta:
        model = Vacation
        fields = [
            'name', 'start_date', 'end_date', 'status', 'notes',
            'airfare_budget', 'lodging_budget', 'meals_budget',
            'excursions_budget', 'gas_budget', 'cruise_budget', 'car_rental_budget', 'misc_budget',
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in [
            'airfare_budget', 'lodging_budget', 'meals_budget',
            'excursions_budget', 'gas_budget', 'cruise_budget', 'car_rental_budget', 'misc_budget',
        ]:
            self.fields[field].widget.attrs.update({'step': '0.01', 'min': '0', 'class': 'form-control'})
        for field in ['name', 'notes']:
            self.fields[field].widget.attrs.update({'class': 'form-control'})


class DayForm(forms.ModelForm):
    class Meta:
        model = Day
        fields = ['date', 'lodging', 'excursion', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'lodging': forms.TextInput(attrs={'class': 'form-control'}),
            'excursion': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['description', 'category', 'amount', 'notes']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional note'}),
        }
