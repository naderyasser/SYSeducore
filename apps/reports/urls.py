from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('attendance/', views.attendance_report, name='attendance'),
    path('payments/', views.payment_report, name='payments'),
]
