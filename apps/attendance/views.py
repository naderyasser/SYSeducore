from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .models import Session, Attendance
from .services import AttendanceService
from apps.students.models import Student
import json


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

        return JsonResponse(result)

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'خطأ في البيانات المرسلة',
            'sound': 'error'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في النظام: {str(e)}',
            'sound': 'error'
        })


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
        session = Session.objects.get(pk=session_id)
        session.teacher_attended = True
        session.teacher_checkin_time = timezone.now()
        session.save()
        
        return JsonResponse({'success': True})
    except Session.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Session not found'}, status=404)


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
