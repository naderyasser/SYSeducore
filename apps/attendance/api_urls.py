from django.urls import path
from . import api_views

urlpatterns = [
    # ``scan/`` (api_views.process_scan) was a broken duplicate of
    # ``attendance:process_student_code`` and always answered 500 — removed
    # together with the view. The scanner UI uses the maintained endpoint.
    path('session/<int:session_id>/', api_views.session_attendance, name='api_session'),
    path('student/<int:student_id>/history/', api_views.student_history, name='api_student_history'),
]
