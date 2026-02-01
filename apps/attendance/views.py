from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from .models import Session, Attendance
from .services import AttendanceService
from apps.students.models import Student
import json
import logging

logger = logging.getLogger(__name__)


@login_required
def scanner_page(request):
    """
    صفحة إدخال كود الطالب (النظام الجديد)
    """
    return render(request, 'attendance/scanner.html', {
        'page_title': 'تسجيل الحضور - إدخال يدوي'
    })


@login_required
@require_http_methods(["POST"])
def process_student_code(request):
    """
    API Endpoint: معالجة كود الطالب

    النظام الجديد: استقبال كود الطالب يدوياً بدلاً من الباركود
    الخوارزمية: 4 خطوات صارمة
    """
    try:
        # قراءة البيانات من الطلب
        data = json.loads(request.body)
        student_code = data.get('student_code', '').strip()

        if not student_code:
            logger.warning(f"Empty student code submitted by {request.user}")
            return JsonResponse({
                'success': False,
                'message': 'الرجاء إدخال كود الطالب',
                'sound': 'error'
            })

        # معالجة الكود باستخدام الخدمة الجديدة
        result = AttendanceService.process_scan(
            student_code=student_code,
            supervisor=request.user
        )

        logger.info(f"Student code {student_code} processed by {request.user}. Result: {result.get('status')}")
        return JsonResponse(result)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in process_student_code: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'خطأ في البيانات المرسلة',
            'sound': 'error'
        }, status=400)
    except Exception as e:
        logger.exception(f"Unexpected error in process_student_code: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'خطأ في النظام',
            'sound': 'error'
        }, status=500)


@login_required
def session_detail(request, session_id):
    """
    تفاصيل الحصة
    """
    session = get_object_or_404(Session, pk=session_id)
    attendances = session.attendances.select_related('student').all()
    return render(request, 'attendance/session_detail.html', {
        'session': session,
        'attendances': attendances
    })


@login_required
@require_http_methods(["POST"])
def record_teacher_attendance(request, session_id):
    """
    تسجيل حضور المدرس
    """
    try:
        session = get_object_or_404(Session, pk=session_id)
        session.teacher_attended = True
        session.teacher_checkin_time = timezone.now()
        session.save(update_fields=['teacher_attended', 'teacher_checkin_time'])
        
        logger.info(f"Teacher attendance recorded for session {session_id} by {request.user}")
        return JsonResponse({'success': True})
    except Session.DoesNotExist:
        logger.warning(f"Session {session_id} not found for teacher attendance")
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)
    except Exception as e:
        logger.error(f"Error recording teacher attendance for session {session_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)


@login_required
@require_http_methods(["POST"])
def cancel_session(request, session_id):
    """
    إلغاء حصة
    """
    try:
        session = Session.objects.get(pk=session_id)
        reason = request.POST.get('reason', '')
        
        session.is_cancelled = True
        session.cancellation_reason = reason
        session.save()
        
        return JsonResponse({'success': True})
    except Session.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)


# ========================================
# Live Monitor Views
# ========================================

@login_required
def live_monitor_dashboard(request):
    """
    Live monitor dashboard for tracking attendance across all rooms
    شاشة المراقبة الحية لتتبع الحضور في جميع القاعات
    """
    from .monitor_service import LiveMonitorService
    
    # Get initial data
    dashboard_data = LiveMonitorService.get_live_dashboard_data(use_cache=True)
    settings = LiveMonitorService.get_monitor_settings()
    
    context = {
        'page_title': 'شاشة المراقبة الحية',
        'dashboard_data': dashboard_data,
        'settings': settings,
    }
    
    return render(request, 'attendance/live_monitor.html', context)


@login_required
def live_monitor_settings(request):
    """
    Live monitor settings page
    صفحة إعدادات الشاشة الحية
    """
    from .monitor_service import LiveMonitorService
    
    if request.method == 'POST':
        # Save settings
        settings = {
            'refresh_interval': int(request.POST.get('refresh_interval', 5)),
            'auto_refresh': request.POST.get('auto_refresh') == 'on',
            'show_alerts': request.POST.get('show_alerts') == 'on',
            'enable_sound': request.POST.get('enable_sound') == 'on',
            'fullscreen_mode': request.POST.get('fullscreen_mode') == 'on',
        }
        
        # TODO: Save to database or user profile
        
        from django.contrib import messages
        messages.success(request, 'تم حفظ الإعدادات بنجاح')
        
    current_settings = LiveMonitorService.get_monitor_settings()
    
    context = {
        'page_title': 'إعدادات الشاشة الحية',
        'settings': current_settings,
    }
    
    return render(request, 'attendance/monitor_settings.html', context)


@require_http_methods(["POST"])
def scan_teacher_qr(request):
    """
    Teacher QR scan endpoint - marks teacher as attended
    """
    try:
        data = json.loads(request.body)
        qr_code = data.get('qr_code', '').strip()
        
        if not qr_code or not qr_code.startswith('TEACHER-'):
            return JsonResponse({
                'success': False,
                'message': 'كود المدرس غير صحيح',
                'color_code': 'red'
            })
        
        # Extract teacher ID
        try:
            teacher_id = int(qr_code.split('-')[1])
        except (IndexError, ValueError):
            return JsonResponse({
                'success': False,
                'message': 'كود المدرس غير صحيح',
                'color_code': 'red'
            })
        
        # Get teacher
        from apps.teachers.models import Teacher
        try:
            teacher = Teacher.objects.get(teacher_id=teacher_id, is_active=True)
        except Teacher.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'المدرس غير موجود',
                'color_code': 'red'
            })
        
        # Get current session for this teacher
        now = timezone.now()
        current_day = now.strftime('%A')
        
        from apps.teachers.models import Group
        groups = Group.objects.filter(
            teacher=teacher,
            schedule_day=current_day,
            is_active=True
        )
        
        session_found = False
        for group in groups:
            # Check if within session time window
            start_time = group.schedule_time
            end_time = (
                timezone.datetime.combine(now.date(), start_time) +
                timezone.timedelta(minutes=group.duration)
            ).time()
            
            current_time = now.time()
            if start_time <= current_time <= end_time:
                # Get or create session
                session, _ = Session.objects.get_or_create(
                    group=group,
                    session_date=now.date()
                )
                
                # Mark teacher as attended
                session.teacher_attended = True
                session.teacher_checkin_time = now
                session.save(update_fields=['teacher_attended', 'teacher_checkin_time'])
                
                session_found = True
                
                logger.info(
                    f"Teacher {teacher.full_name} checked in for session "
                    f"{session.session_id} at {now}"
                )
                
                return JsonResponse({
                    'success': True,
                    'message': f'مرحباً {teacher.full_name}\nتم تسجيل حضورك بنجاح',
                    'color_code': 'green',
                    'teacher_name': teacher.full_name,
                    'group_name': group.group_name,
                    'session_time': start_time.strftime('%H:%M')
                })
        
        if not session_found:
            return JsonResponse({
                'success': False,
                'message': f'{teacher.full_name}\nلا توجد حصة مجدولة الآن',
                'color_code': 'white'
            })
    
    except Exception as e:
        logger.exception(f"Error in teacher QR scan: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'خطأ في النظام',
            'color_code': 'red'
        })


@require_http_methods(["GET"])
def kiosk_current_session(request, device_id):
    """
    API endpoint for kiosk to get current session info
    """
    try:
        from .models import KioskDevice
        
        kiosk = get_object_or_404(KioskDevice, device_id=device_id, is_active=True)
        
        # Update heartbeat
        kiosk.last_heartbeat = timezone.now()
        kiosk.save(update_fields=['last_heartbeat'])
        
        # Get current session
        session = kiosk.get_current_session()
        
        if not session:
            return JsonResponse({
                'has_session': False,
                'message': 'لا توجد حصة حالياً في هذه القاعة'
            })
        
        # Get session details
        group = session.group
        
        # Count attendance
        total_students = group.enrollments.filter(is_active=True).count()
        attended_count = Attendance.objects.filter(
            session=session,
            allow_entry=True
        ).count()
        
        return JsonResponse({
            'has_session': True,
            'session_id': session.session_id,
            'group_name': group.group_name,
            'teacher_name': group.teacher.full_name,
            'room_name': group.room.name,
            'schedule_time': group.schedule_time.strftime('%H:%M'),
            'duration': group.duration,
            'total_students': total_students,
            'attended_count': attended_count,
            'is_cancelled': session.is_cancelled,
            'cancellation_reason': session.cancellation_reason if session.is_cancelled else None
        })
    
    except Exception as e:
        logger.exception(f"Error getting kiosk session: {str(e)}")
        return JsonResponse({
            'has_session': False,
            'error': 'خطأ في النظام'
        }, status=500)

