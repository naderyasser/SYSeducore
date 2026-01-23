from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from .models import Session, Attendance
from apps.students.models import Student


@login_required
def scanner_page(request):
    """
    صفحة مسح الباركود
    """
    return render(request, 'attendance/scanner.html', {
        'page_title': 'تسجيل الحضور'
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
