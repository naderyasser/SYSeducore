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


@login_required
@require_http_methods(["GET"])
def live_dashboard_status(request):
    """
    API endpoint for live dashboard status
    نقطة نهاية API لحالة الشاشة الحية
    """
    from .monitor_service import LiveMonitorService
    
    try:
        data = LiveMonitorService.get_live_dashboard_data(use_cache=True)
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def live_room_detail(request, room_id):
    """
    API endpoint for detailed room attendance
    نقطة نهاية API لتفاصيل حضور القاعة
    """
    from .monitor_service import LiveMonitorService
    
    try:
        data = LiveMonitorService.get_room_detail(room_id)
        
        if data is None:
            return JsonResponse({
                'success': False,
                'error': 'Room not found'
            }, status=404)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def live_monitor_settings(request):
    """
    API endpoint for monitor settings
    نقطة نهاية API لإعدادات الشاشة
    """
    from .monitor_service import LiveMonitorService
    
    try:
        settings = LiveMonitorService.get_monitor_settings()
        return JsonResponse({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def today_sessions_api(request):
    """
    API endpoint for getting today's sessions as JSON.
    Returns groups scheduled for today based on their schedule_day.
    """
    from django.utils import timezone
    from apps.teachers.models import Group
    from datetime import datetime, timedelta

    today = timezone.now().date()

    # Map Python weekday (0=Monday) to model day names
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    today_day = day_names[today.weekday()]

    # Get groups scheduled for today
    groups = Group.objects.filter(
        schedule_day=today_day,
        is_active=True
    ).select_related('teacher', 'room').order_by('schedule_time')

    sessions_data = []
    now = datetime.now().time()

    for group in groups:
        # Calculate if session is currently active
        schedule_time = group.schedule_time
        duration = getattr(group, 'session_duration', 120) or 120  # Default 2 hours

        start_datetime = datetime.combine(today, schedule_time)
        end_datetime = start_datetime + timedelta(minutes=duration)
        end_time = end_datetime.time()

        is_active = schedule_time <= now <= end_time
        is_past = now > end_time

        sessions_data.append({
            'id': group.group_id,
            'group_name': group.group_name,
            'teacher_name': group.teacher.full_name if group.teacher else 'N/A',
            'room_name': group.room.name if group.room else 'N/A',
            'time': schedule_time.strftime('%H:%M'),
            'day': today.strftime('%Y-%m-%d'),
            'status': 'active' if is_active else ('completed' if is_past else 'scheduled'),
        })

    return JsonResponse({'sessions': sessions_data})


@login_required
@require_http_methods(["GET"])
def live_printable_report(request):
    """
    API endpoint for printable status report
    نقطة نهاية API لتقرير الحالة القابل للطباعة
    """
    from .monitor_service import LiveMonitorService
    
    try:
        data = LiveMonitorService.get_printable_report()
        return JsonResponse({
            'success': True,
            'data': data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
