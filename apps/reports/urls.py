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
    
    # Recycle Bin - سلة المهملات
    path('recycle-bin/', views.recycle_bin, name='recycle_bin'),
    path('recycle-bin/restore/', views.recycle_restore, name='recycle_restore'),
    path('recycle-bin/delete/', views.recycle_permanent_delete, name='recycle_permanent_delete'),
    path('recycle-bin/empty/', views.recycle_empty, name='recycle_empty'),
]
