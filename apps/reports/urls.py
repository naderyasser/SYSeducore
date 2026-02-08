from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('attendance/', views.attendance_report, name='attendance'),
    path('password/', views.password_prompt, name='password_prompt'),
    path('password/verify/', views.verify_password, name='verify_password'),
    path('logout/', views.clear_report_session, name='logout'),
    path('payments/', views.payment_report, name='payments'),
    path('financial/', views.financial_report, name='financial'),
]
