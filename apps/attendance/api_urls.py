from django.urls import path
from . import api_views

urlpatterns = [
    path('scan/', api_views.process_scan, name='api_scan'),
    path('session/<int:session_id>/', api_views.session_attendance, name='api_session'),
    path('student/<int:student_id>/history/', api_views.student_history, name='api_student_history'),
    path('sessions/today/', api_views.today_sessions_api, name='api_today_sessions'),
    
    # Live Monitor endpoints
    path('monitor/live-status/', api_views.live_dashboard_status, name='api_live_status'),
    path('monitor/room/<int:room_id>/', api_views.live_room_detail, name='api_live_room_detail'),
    path('monitor/settings/', api_views.live_monitor_settings, name='api_live_settings'),
    path('monitor/print-report/', api_views.live_printable_report, name='api_live_print_report'),
]
