from django.urls import path
from . import views
from . import htmx_views

app_name = 'attendance'

urlpatterns = [
    # ========================================
    # HTMX-Powered Views (New)
    # ========================================
    
    # Scanner select page
    path('scanner/select/', htmx_views.scanner_select, name='scanner_select'),
    
    # Scanner page for specific session (Normal Mode)
    path('scanner/<int:session_id>/', htmx_views.scanner_page, name='scanner_page'),
    
    # Kiosk Mode Scanner (Full Screen Colored Display)
    path('scanner/<int:session_id>/kiosk/', htmx_views.kiosk_scanner_page, name='kiosk_scanner'),
    
    # HTMX API endpoints
    path('htmx/api/scan/', htmx_views.api_scan, name='htmx_api_scan'),
    path('htmx/api/session/<int:session_id>/attendance/', htmx_views.api_session_attendance, name='htmx_api_session_attendance'),
    path('htmx/api/session/<int:session_id>/stats/', htmx_views.api_session_stats, name='htmx_api_session_stats'),
    path('htmx/api/sessions/today/', htmx_views.api_today_sessions, name='htmx_api_today_sessions'),
    
    # ========================================
    # Legacy Views (Keep for compatibility)
    # ========================================
    
    # صفحة الإدخال اليدوي (legacy - redirects to select)
    path('scanner/', views.scanner_page, name='scanner'),

    # API: معالجة كود الطالب (النظام الجديد)
    path('api/process-code/', views.process_student_code, name='process_student_code'),

    # تفاصيل الحصة
    path('session/<int:session_id>/', views.session_detail, name='session_detail'),

    # تسجيل حضور المدرس
    path('api/teacher-checkin/<int:session_id>/', views.record_teacher_attendance, name='teacher_checkin'),

    # إلغاء الحصة
    path('api/cancel-session/<int:session_id>/', views.cancel_session, name='cancel_session'),
    
    # ========================================
    # Live Monitor Views
    # ========================================
    
    # Live monitor dashboard
    path('monitor/', views.live_monitor_dashboard, name='live_monitor'),
    
    # Live monitor settings
    path('monitor/settings/', views.live_monitor_settings, name='live_monitor_settings'),
    
    # ========================================
    # Teacher & Kiosk APIs
    # ========================================
    
    # Teacher QR scan endpoint
    path('api/scan-teacher/', views.scan_teacher_qr, name='scan_teacher_qr'),
    
    # Kiosk current session API
    path('api/kiosk/<str:device_id>/current-session/', views.kiosk_current_session, name='kiosk_current_session'),
]
