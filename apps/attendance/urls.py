from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    # صفحة الإدخال اليدوي
    path('scanner/', views.scanner_page, name='scanner'),

    # API: معالجة كود الطالب (النظام الجديد)
    path('api/process-code/', views.process_student_code, name='process_student_code'),

    # تفاصيل الحصة
    path('session/<int:session_id>/', views.session_detail, name='session_detail'),

    # تسجيل حضور المدرس
    path('api/teacher-checkin/<int:session_id>/', views.record_teacher_attendance, name='teacher_checkin'),

    # إلغاء الحصة
    path('api/cancel-session/<int:session_id>/', views.cancel_session, name='cancel_session'),
]
