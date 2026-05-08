from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),

    # Vacations
    path('vacations/new/', views.VacationCreateView.as_view(), name='vacation_create'),
    path('vacations/<int:pk>/', views.VacationDetailView.as_view(), name='vacation_detail'),
    path('vacations/<int:pk>/edit/', views.VacationEditView.as_view(), name='vacation_edit'),
    path('vacations/<int:pk>/delete/', views.VacationDeleteView.as_view(), name='vacation_delete'),

    # Days
    path('vacations/<int:vacation_pk>/days/add/', views.DayCreateView.as_view(), name='day_create'),
    path('days/<int:pk>/edit/', views.DayEditView.as_view(), name='day_edit'),
    path('days/<int:pk>/delete/', views.DayDeleteView.as_view(), name='day_delete'),

    # Expenses
    path('days/<int:day_pk>/expenses/add/', views.ExpenseCreateView.as_view(), name='expense_create'),
    path('expenses/<int:pk>/edit/', views.ExpenseEditView.as_view(), name='expense_edit'),
    path('expenses/<int:pk>/delete/', views.ExpenseDeleteView.as_view(), name='expense_delete'),

    # Offline sync API
    path('api/expenses/', views.ExpenseCreateApiView.as_view(), name='api_expense_create'),

    # Savings
    path('savings/update/', views.UpdateSavingsView.as_view(), name='savings_update'),
]
