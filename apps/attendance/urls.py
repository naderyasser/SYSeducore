from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    # صفحة الإدخال اليدوي
    path('scanner/', views.scanner_page, name='scanner'),

    # API: معالجة كود الطالب (النظام الجديد)
    path('api/process-code/', views.process_student_code, name='process_student_code'),

    # API: إحصائيات اليوم
    path('api/today-stats/', views.today_stats, name='today_stats'),

    # API: حصص اليوم
    path('api/today-sessions/', views.today_sessions, name='today_sessions'),

    # API: تصدير التقارير
    path('api/export-report/', views.export_report, name='export_report'),

    # تفاصيل الحصة
    path('session/<int:session_id>/', views.session_detail, name='session_detail'),

    # تسجيل حضور المدرس
    path('api/teacher-checkin/<int:session_id>/', views.record_teacher_attendance, name='teacher_checkin'),

    # إلغاء الحصة
    path('api/cancel-session/<int:session_id>/', views.cancel_session, name='cancel_session'),

    # Scanner Quick Actions
    path('api/scanner-pay-now/', views.scanner_pay_now, name='scanner_pay_now'),
    path('api/scanner-grace-period/', views.scanner_grace_period, name='scanner_grace_period'),

    # Exception Handling (Estesna)
    path('api/grant-exception/', views.grant_exception, name='grant_exception'),
    path('api/exception-reasons/', views.exception_reasons_list, name='exception_reasons_list'),
    path('api/revoke-exception/<int:exception_id>/', views.revoke_exception, name='revoke_exception'),
]
