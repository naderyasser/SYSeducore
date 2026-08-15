from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('attendance/', views.attendance_report, name='attendance'),

    # NOTE: the ``password/``, ``password/verify/`` and ``logout/`` routes were
    # removed along with the inert "report password" gate (SEC-07). The gate
    # let every authenticated user straight through, so the financial reports
    # were never actually protected; they are guarded by role decorators now.
    path('payments/', views.payment_report, name='payments'),
    path('financial/', views.financial_report, name='financial'),
    path('tsfya/', views.monthly_financial_summary, name='tsfya'),

    # Activity Log - سجل النشاط
    path('activity-log/', views.activity_log, name='activity_log'),

    # Recycle Bin - سلة المهملات
    path('recycle-bin/', views.recycle_bin, name='recycle_bin'),
    path('recycle-bin/restore/', views.recycle_restore, name='recycle_restore'),
    path('recycle-bin/delete/', views.recycle_permanent_delete, name='recycle_permanent_delete'),
    path('recycle-bin/empty/', views.recycle_empty, name='recycle_empty'),
]
