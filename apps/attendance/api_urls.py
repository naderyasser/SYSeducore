from django.urls import path
from . import api_views

urlpatterns = [
    path('scan/', api_views.process_scan, name='api_scan'),
    path('session/<int:session_id>/', api_views.session_attendance, name='api_session'),
    path('student/<int:student_id>/history/', api_views.student_history, name='api_student_history'),
]
