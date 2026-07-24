from django.http import JsonResponse
from django.utils import timezone

from apps.accounts.decorators import ajax_login_required

# ``process_scan`` used to live here as a second, broken copy of the scanner
# endpoint: it treated ``AttendanceService.process_scan()['student']`` as a
# model instance when the service returns a plain dict, so every call raised
# AttributeError and answered 500. Nothing reached it — the scanner UI posts to
# ``attendance:process_student_code`` (``views.process_student_code``), which is
# the maintained implementation. The duplicate and its ``/api/attendance/scan/``
# route were removed rather than fixed twice over.


@ajax_login_required
def session_attendance(request, session_id):
    """
    API endpoint لجلب حضور الحصة
    """
    from .models import Session
    try:
        session = Session.objects.select_related('group').get(pk=session_id)
        attendances = session.attendances.select_related('student').all()
        
        data = {
            'success': True,
            'session': {
                'id': session.session_id,
                'date': session.session_date.isoformat(),
                'group': session.group.group_name,
                'teacher_attended': session.teacher_attended,
            },
            'attendances': [
                {
                    'id': a.attendance_id,
                    'student': a.student.full_name,
                    'status': a.status,
                    'scan_time': timezone.localtime(a.scan_time).isoformat(),
                }
                for a in attendances
            ]
        }
        return JsonResponse(data)
    except Session.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Session not found'
        }, status=404)


@ajax_login_required
def student_history(request, student_id):
    """
    API endpoint لجلب سجل حضور الطالب
    """
    from apps.students.models import Student
    try:
        student = Student.objects.get(pk=student_id)
        attendances = student.attendances.select_related('session').order_by('-scan_time')[:20]
        
        data = {
            'success': True,
            'student': {
                'id': student.student_id,
                'name': student.full_name,
                'student_code': student.student_code,
            },
            'attendances': [
                {
                    'id': a.attendance_id,
                    'date': a.session.session_date.isoformat(),
                    'status': a.status,
                    'scan_time': timezone.localtime(a.scan_time).isoformat(),
                }
                for a in attendances
            ]
        }
        return JsonResponse(data)
    except Student.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Student not found'
        }, status=404)
