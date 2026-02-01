"""
HTMX Views for Attendance App
Returns HTML fragments for HTMX requests - STRICT MODE
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.contrib import messages
from .models import Session, Attendance
from .services import AttendanceService
from apps.teachers.models import Group
import json


@login_required
def scanner_select(request):
    """
    Page to select a session for scanning
    """
    today = timezone.now().date()
    
    # Get today's sessions
    sessions = Session.objects.filter(
        session_date=today,
        is_cancelled=False
    ).select_related('group__teacher', 'group__room')
    
    # Get all active groups for creating new sessions
    all_groups = Group.objects.filter(is_active=True).select_related('teacher')
    
    return render(request, 'attendance/scanner_select.html', {
        'sessions': sessions,
        'today': today,
        'all_groups': all_groups,
    })


@login_required
@require_POST
def create_session(request):
    """
    Create a new session for a group
    """
    group_id = request.POST.get('group_id')
    session_date = request.POST.get('session_date')
    
    if not group_id:
        messages.error(request, 'يجب اختيار المجموعة')
        return redirect('attendance:scanner_select')
    
    try:
        group = Group.objects.get(group_id=group_id)
    except Group.DoesNotExist:
        messages.error(request, 'المجموعة غير موجودة')
        return redirect('attendance:scanner_select')
    
    # Parse date or use today
    if session_date:
        from datetime import datetime
        session_date = datetime.strptime(session_date, '%Y-%m-%d').date()
    else:
        session_date = timezone.now().date()
    
    # Check if session already exists
    existing = Session.objects.filter(group=group, session_date=session_date).first()
    if existing:
        messages.info(request, f'الجلسة موجودة بالفعل - {group.group_name}')
        return redirect('attendance:scanner_page', session_id=existing.session_id)
    
    # Create session
    session = Session.objects.create(
        group=group,
        session_date=session_date,
        is_cancelled=False
    )
    
    messages.success(request, f'تم إنشاء جلسة جديدة - {group.group_name}')
    return redirect('attendance:scanner_page', session_id=session.session_id)


@login_required
def scanner_page(request, session_id):
    """
    Scanner page for a specific session (Normal Mode)
    """
    session = get_object_or_404(Session, pk=session_id)
    group = session.group
    
    # Get all enrolled students for this group
    from apps.students.models import StudentGroupEnrollment
    enrollments = StudentGroupEnrollment.objects.filter(
        group=group,
        is_active=True
    ).select_related('student')
    
    # Get current attendance stats
    attendances = session.attendances.all()
    stats = {
        'total': enrollments.count(),
        'present': attendances.filter(status='present', allow_entry=True).count(),
        'late': attendances.filter(status='late_blocked').count(),
        'absent': enrollments.count() - attendances.count()
    }
    
    return render(request, 'attendance/scanner.html', {
        'session_id': session_id,
        'group_name': group.group_name,
        'session_date': session.session_date,
        'total_students': stats['total'],
        'stats': stats
    })


@login_required
def kiosk_scanner_page(request, session_id):
    """
    Kiosk Mode Scanner - Full screen colored display
    """
    session = get_object_or_404(Session, pk=session_id)
    group = session.group
    
    return render(request, 'attendance/kiosk_scanner.html', {
        'session_id': session_id,
        'group_name': group.group_name,
        'session_date': session.session_date.strftime('%Y-%m-%d'),
        'schedule_time': group.schedule_time.strftime('%I:%M %p')
    })


@login_required
@require_http_methods(["POST"])
def api_scan(request):
    """
    HTMX endpoint for processing barcode scan
    Returns HTML fragment based on scan result
    """
    try:
        data = json.loads(request.body)
        barcode = data.get('barcode', '').strip()
        session_id = data.get('session_id')
        is_kiosk = data.get('kiosk_mode', False)
        
        if not barcode:
            if is_kiosk:
                template = 'attendance/partials/kiosk_gray.html'
            else:
                template = 'attendance/partials/scan_result_error.html'
            result_html = render_to_string(template, {
                'message': 'الرجاء إدخال كود الطالب',
                'time': timezone.now().strftime('%H:%M:%S')
            })
            return HttpResponse(result_html, status=400)
        
        # Process the scan
        result = AttendanceService.process_scan(
            student_code=barcode,
            supervisor=request.user
        )
        
        # Determine which template to render based on result
        if is_kiosk:
            # Kiosk mode - use full-screen colored templates
            if result['success']:
                template = 'attendance/partials/kiosk_green.html'
            elif result['status'] == 'late_blocked':
                template = 'attendance/partials/kiosk_red_late.html'
            elif result['status'] == 'very_late':
                template = 'attendance/partials/kiosk_red_very_late.html'
            elif result['status'] == 'blocked_payment':
                template = 'attendance/partials/kiosk_yellow.html'
            elif result['status'] == 'no_session':
                template = 'attendance/partials/kiosk_white.html'
            else:
                template = 'attendance/partials/kiosk_gray.html'
        else:
            # Normal mode - use smaller alert templates
            if result['success']:
                template = 'attendance/partials/scan_result_success.html'
            elif result['status'] in ['late_blocked', 'very_late']:
                template = 'attendance/partials/scan_result_error.html'
            elif result['status'] == 'blocked_payment':
                template = 'attendance/partials/scan_result_warning.html'
            else:
                template = 'attendance/partials/scan_result_error.html'
        
        # Render the template with result data
        result_html = render_to_string(template, {
            'student_name': result.get('student_name', ''),
            'message': result.get('message', ''),
            'time': result.get('time', timezone.now().strftime('%H:%M:%S')),
            'status': result.get('status', ''),
            'success': result.get('success', False),
            'color_code': result.get('color_code', 'gray'),
            'allow_entry': result.get('allow_entry', False),
            'minutes_late': result.get('minutes_late', 0),
            'group_name': result.get('group_name', ''),
            'reason': result.get('reason', '')
        })
        
        status_code = 200 if result['success'] else 400
        return HttpResponse(result_html, status=status_code)
        
    except Exception as e:
        result_html = render_to_string('attendance/partials/kiosk_gray.html', {
            'message': f'خطأ في النظام: {str(e)}',
            'time': timezone.now().strftime('%H:%M:%S')
        })
        return HttpResponse(result_html, status=500)


@login_required
def api_session_attendance(request, session_id):
    """
    HTMX endpoint for getting session attendance list
    Returns HTML table rows
    """
    session = get_object_or_404(Session, pk=session_id)
    attendances = session.attendances.select_related('student').all()
    
    # Get all enrolled students
    from apps.students.models import StudentGroupEnrollment
    enrollments = StudentGroupEnrollment.objects.filter(
        group=session.group,
        is_active=True
    ).select_related('student')
    
    rows_html = render_to_string('attendance/partials/attendance_rows.html', {
        'session': session,
        'attendances': attendances,
        'enrollments': enrollments
    })
    
    return HttpResponse(rows_html)


@login_required
def api_today_sessions(request):
    """
    HTMX endpoint for getting today's sessions
    Returns HTML list items
    """
    today = timezone.now().date()
    sessions = Session.objects.filter(
        session_date=today,
        is_cancelled=False
    ).select_related('group__teacher')
    
    html = render_to_string('attendance/partials/session_list.html', {
        'sessions': sessions
    })
    
    return HttpResponse(html)


@login_required
def api_session_stats(request, session_id):
    """
    HTMX endpoint for getting session statistics
    Returns JSON with stats
    """
    from django.http import JsonResponse
    
    session = get_object_or_404(Session, pk=session_id)
    attendances = session.attendances.all()
    
    stats = {
        'total': attendances.count(),
        'present': attendances.filter(status='present', allow_entry=True).count(),
        'late_blocked': attendances.filter(status='late_blocked').count(),
        'very_late': attendances.filter(status='very_late').count(),
        'payment_blocked': attendances.filter(status='blocked_payment').count(),
        'no_session': attendances.filter(status='no_session').count(),
        'other_blocked': attendances.filter(status='blocked_other').count(),
    }
    
    return JsonResponse(stats)
