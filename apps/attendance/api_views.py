from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
import json
from .services import AttendanceService


@login_required
@require_http_methods(["POST"])
def process_scan(request):
    """
    API endpoint لمعالجة مسح الباركود
    """
    try:
        data = json.loads(request.body)
        barcode = data.get('barcode')
        
        if not barcode:
            return JsonResponse({
                'success': False,
                'message': 'الباركود مطلوب'
            }, status=400)
        
        result = AttendanceService.process_scan(barcode, request.user)
        
        # تحويل الكائنات إلى dict
        if result.get('success') and 'student' in result:
            result['student'] = {
                'id': result['student'].student_id,
                'name': result['student'].full_name,
                'barcode': result['student'].barcode
            }
            if 'attendance' in result:
                result['attendance'] = {
                    'id': result['attendance'].attendance_id,
                    'status': result['attendance'].status,
                    'scan_time': result['attendance'].scan_time.isoformat()
                }
        
        status_code = 200 if result['success'] else 400
        return JsonResponse(result, status=status_code)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'بيانات غير صالحة'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': 'حدث خطأ في الخادم'
        }, status=500)


@login_required
def session_attendance(request, session_id):
    """
    API endpoint لجلب حضور الحصة
    """
    from .models import Session, Attendance
    try:
        session = Session.objects.get(pk=session_id)
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
                    'scan_time': a.scan_time.isoformat(),
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


@login_required
def student_history(request, student_id):
    """
    API endpoint لجلب سجل حضور الطالب
    """
    from .models import Attendance
    from apps.students.models import Student
    try:
        student = Student.objects.get(pk=student_id)
        attendances = student.attendances.select_related('session').order_by('-scan_time')[:20]
        
        data = {
            'success': True,
            'student': {
                'id': student.student_id,
                'name': student.full_name,
                'barcode': student.barcode,
            },
            'attendances': [
                {
                    'id': a.attendance_id,
                    'date': a.session.session_date.isoformat(),
                    'status': a.status,
                    'scan_time': a.scan_time.isoformat(),
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
