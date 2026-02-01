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
