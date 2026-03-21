from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import models
from django.db.models import Sum, Count, Q, F, Avg
from django.db.models.functions import TruncDate, TruncMonth
from django.http import JsonResponse
from datetime import timedelta, datetime
from collections import defaultdict
import json
import functools
from django.contrib import messages
from decouple import config

from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room
from apps.attendance.models import Attendance, Session, ActivityLog
from apps.payments.models import Payment


# Password for accessing sensitive reports
REPORTS_PASSWORD = config('REPORTS_PASSWORD', default='0000')


def report_password_required(view_func):
    """
    Decorator to require password for accessing sensitive reports.
    Checks session for password verification.
    """
    @functools.wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Admin users bypass password requirement
        if hasattr(request, 'user') and request.user.is_authenticated and request.user.role == 'admin':
            return view_func(request, *args, **kwargs)
        if not request.session.get('report_authenticated'):
            # Save the original URL to redirect back after authentication
            request.session['report_redirect_after'] = request.get_full_path()
            return redirect('reports:password_prompt')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@login_required
def password_prompt(request):
    """
    Display password entry form for accessing protected reports.
    """
    return render(request, 'reports/password_prompt.html')


@login_required
def verify_password(request):
    """
    Verify the password and grant access if correct.
    """
    if request.method == 'POST':
        password = request.POST.get('password', '')
        if password == REPORTS_PASSWORD:
            request.session['report_authenticated'] = True
            # Set session to expire after 1 hour
            request.session.set_expiry(3600)

            # Redirect to the originally requested URL or dashboard
            redirect_url = request.session.get('report_redirect_after')
            if redirect_url:
                del request.session['report_redirect_after']
                return redirect(redirect_url)
            return redirect('reports:dashboard')
        else:
            messages.error(request, 'Incorrect password. Please try again.')

    return redirect('reports:password_prompt')


@login_required
def clear_report_session(request):
    """
    Clear the report authentication session.
    """
    if 'report_authenticated' in request.session:
        del request.session['report_authenticated']
    messages.success(request, 'You have been logged out from reports access.')
    return redirect('reports:dashboard')


def AttendanceService_get_day_name():
    """Helper to get current day name"""
    days_map = {
        0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
        3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday',
    }
    return days_map.get(timezone.now().weekday(), '')


@login_required
def dashboard(request):
    """
    Professional Dashboard with comprehensive statistics, charts,
    schedule widget, and activity log
    """
    today = timezone.now().date()
    this_month_start = today.replace(day=1)
    current_day_name = AttendanceService_get_day_name()

    # ====== KEY METRICS ======
    total_students = Student.objects.filter(is_active=True).count()
    total_teachers = Teacher.objects.filter(is_active=True).count()
    total_rooms = Room.objects.filter(is_active=True).count()
    total_active_groups = Group.objects.filter(is_active=True).count()

    # New students this month
    new_students_this_month = Student.objects.filter(
        is_active=True,
        created_at__date__gte=this_month_start
    ).count()

    # ====== TODAY'S OVERVIEW ======
    # Today's sessions
    today_sessions = Session.objects.filter(session_date=today, group__is_active=True)
    today_active_sessions = today_sessions.filter(is_cancelled=False).count()
    today_cancelled_sessions = today_sessions.filter(is_cancelled=True).count()

    # Today's attendance
    today_attendances = Attendance.objects.filter(session__session_date=today)
    today_present = today_attendances.filter(status='present').count()
    today_late = today_attendances.filter(status='late').count()
    today_absent = today_attendances.filter(status='absent').count()
    today_total_attendance = today_present + today_late + today_absent
    today_attendance_rate = ((today_present + today_late) / today_total_attendance * 100) if today_total_attendance > 0 else 0

    # Students absent today
    absent_today = today_attendances.filter(status='absent').select_related('student', 'session__group')[:5]

    # ====== FINANCIAL SUMMARY ======
    this_month_payments = Payment.objects.filter(month__gte=this_month_start)
    month_total_due = this_month_payments.aggregate(total=Sum('amount_due'))['total'] or 0
    month_total_paid = this_month_payments.aggregate(total=Sum('amount_paid'))['total'] or 0
    month_remaining = month_total_due - month_total_paid
    collection_rate = (month_total_paid / month_total_due * 100) if month_total_due > 0 else 0

    # Pending payments (unpaid + partial)
    pending_payments_count = this_month_payments.filter(status__in=['unpaid', 'partial']).count()
    pending_payments_list = Payment.objects.filter(
        status__in=['unpaid', 'partial']
    ).select_related('student', 'group').order_by('-month')[:5]

    # Recent payments
    recent_payments = Payment.objects.select_related('student', 'group').filter(
        status__in=['paid', 'partial']
    ).order_by('-payment_date')[:5]

    # ====== TODAY'S SCHEDULE ======
    todays_groups = Group.objects.filter(
        is_active=True,
        schedule_day=current_day_name
    ).select_related('teacher', 'room').annotate(
        enrolled_count=Count(
            'studentgroupenrollment',
            filter=Q(studentgroupenrollment__is_active=True)
        )
    ).order_by('schedule_time')

    today_schedule = []
    now = timezone.now()
    current_time = now.time()

    for grp in todays_groups:
        enrolled_count = grp.enrolled_count
        capacity = grp.room.capacity if grp.room else 0
        end_time = grp.get_end_time()

        # Determine session status
        session_status = 'upcoming'
        if current_time > end_time:
            session_status = 'completed'
        elif current_time >= grp.schedule_time:
            session_status = 'ongoing'

        today_schedule.append({
            'id': grp.group_id,
            'group_name': grp.group_name,
            'teacher': grp.teacher.full_name,
            'room': grp.room.name if grp.room else '-',
            'time_start': grp.schedule_time.strftime('%I:%M %p'),
            'time_end': end_time.strftime('%I:%M %p'),
            'duration': grp.get_duration_display(),
            'enrolled': enrolled_count,
            'capacity': capacity,
            'utilization': (enrolled_count / capacity * 100) if capacity > 0 else 0,
            'status': session_status,
        })

    # ====== WEEK ATTENDANCE TREND ======
    week_attendance_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        day_attendances = Attendance.objects.filter(session__session_date=date)
        total = day_attendances.count()
        present = day_attendances.filter(status='present').count()
        late = day_attendances.filter(status='late').count()
        absent = day_attendances.filter(status='absent').count()
        attendance_rate = ((present + late) / total * 100) if total > 0 else 0

        week_attendance_data.append({
            'date': date.strftime('%a'),
            'full_date': date.strftime('%Y-%m-%d'),
            'present': present,
            'late': late,
            'absent': absent,
            'rate': round(attendance_rate, 1),
        })

    # ====== RECENT ACTIVITY ======
    recent_attendances = Attendance.objects.select_related(
        'student', 'session__group'
    ).order_by('-scan_time')[:6]

    # Activity log
    recent_activities = ActivityLog.objects.select_related('user').order_by('-created_at')[:10]

    # ====== GROUPS STATUS ======
    # Groups with low enrollment
    groups_low_enrollment = []
    groups_high_enrollment = []

    for group in Group.objects.filter(is_active=True).select_related('teacher', 'room').annotate(
        enrolled=Count('studentgroupenrollment', filter=Q(studentgroupenrollment__is_active=True))
    ):
        capacity = group.room.capacity if group.room else 0
        utilization = (group.enrolled / capacity * 100) if capacity > 0 else 0

        group_info = {
            'name': group.group_name,
            'teacher': group.teacher.full_name if group.teacher else '-',
            'enrolled': group.enrolled,
            'capacity': capacity,
            'utilization': utilization,
        }

        if utilization < 50:
            groups_low_enrollment.append(group_info)
        elif utilization >= 90:
            groups_high_enrollment.append(group_info)

    # ====== QUICK STATS ======
    total_rooms_count = Room.objects.filter(is_active=True).count()

    context = {
        # Key Metrics
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_rooms': total_rooms_count,
        'total_groups': total_active_groups,
        'new_students_this_month': new_students_this_month,

        # Today's Overview
        'today_date': today,
        'today_day_name': current_day_name,
        'today_total_sessions': today_sessions.count(),
        'today_active_sessions': today_active_sessions,
        'today_cancelled_sessions': today_cancelled_sessions,
        'today_present': today_present,
        'today_late': today_late,
        'today_absent': today_absent,
        'today_total_attendance': today_total_attendance,
        'today_attendance_rate': round(today_attendance_rate, 1),
        'absent_today': absent_today,

        # Financial
        'month_total_due': month_total_due,
        'month_total_paid': month_total_paid,
        'month_remaining': month_remaining,
        'collection_rate': round(collection_rate, 1),
        'pending_payments_count': pending_payments_count,
        'pending_payments_list': pending_payments_list,
        'recent_payments': recent_payments,

        # Schedule
        'today_schedule': today_schedule,

        # Charts
        'week_attendance_json': json.dumps(week_attendance_data, ensure_ascii=False),

        # Recent Activity
        'recent_attendances': recent_attendances,
        'recent_activities': recent_activities,

        # Groups Status
        'groups_low_enrollment': groups_low_enrollment[:3],
        'groups_high_enrollment': groups_high_enrollment[:3],
    }

    return render(request, 'reports/dashboard.html', context)


@login_required
def attendance_report(request):
    """
    Comprehensive Attendance Report with filters and statistics
    """
    from django.core.paginator import Paginator
    
    # Get filter parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    group_id = request.GET.get('group')
    status = request.GET.get('status')
    
    # Base queryset
    attendances = Attendance.objects.select_related(
        'student', 'session', 'session__group', 'session__group__teacher'
    ).order_by('-scan_time')
    
    # Apply filters
    if date_from:
        attendances = attendances.filter(session__session_date__gte=date_from)
    if date_to:
        attendances = attendances.filter(session__session_date__lte=date_to)
    if group_id:
        attendances = attendances.filter(session__group__group_id=group_id)
    if status:
        attendances = attendances.filter(status=status)
    
    # Statistics
    total_count = attendances.count()
    present_count = attendances.filter(status='present').count()
    late_count = attendances.filter(status='late').count()
    absent_count = attendances.filter(status='absent').count()
    
    # Group filter options
    groups = Group.objects.filter(is_active=True)
    
    # Pagination
    paginator = Paginator(attendances, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_count': total_count,
        'present_count': present_count,
        'late_count': late_count,
        'absent_count': absent_count,
        'groups': groups,
        'date_from': date_from,
        'date_to': date_to,
        'selected_group': group_id,
        'selected_status': status,
    }
    
    return render(request, 'reports/attendance.html', context)


@login_required
@report_password_required
def payment_report(request):
    """
    Comprehensive Payment Report with filters and statistics
    """
    from django.core.paginator import Paginator
    
    # Get filter parameters
    month = request.GET.get('month')
    status = request.GET.get('status')
    group_id = request.GET.get('group')
    
    # Base queryset
    payments = Payment.objects.select_related(
        'student', 'group'
    ).order_by('-month', '-payment_date')
    
    # Apply filters
    if month:
        payments = payments.filter(month__startswith=month)
    if status:
        payments = payments.filter(status=status)
    if group_id:
        payments = payments.filter(group__group_id=group_id)
    
    # Statistics
    total_due = payments.aggregate(Sum('amount_due'))['amount_due__sum'] or 0
    total_paid = payments.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
    total_remaining = total_due - total_paid
    
    # Status counts
    paid_count = payments.filter(status='paid').count()
    partial_count = payments.filter(status='partial').count()
    unpaid_count = payments.filter(status='unpaid').count()
    
    # Group filter options
    groups = Group.objects.filter(is_active=True)
    
    # Pagination
    paginator = Paginator(payments, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_due': total_due,
        'total_paid': total_paid,
        'total_remaining': total_remaining,
        'paid_count': paid_count,
        'partial_count': partial_count,
        'unpaid_count': unpaid_count,
        'groups': groups,
        'selected_month': month,
        'selected_status': status,
        'selected_group': group_id,
    }
    
    return render(request, 'reports/payments.html', context)


@login_required
@report_password_required
def financial_report(request):
    """
    Detailed Financial Report
    """
    today = timezone.now().date()
    this_month = today.replace(day=1)
    
    # Monthly summary for the last 12 months
    monthly_data = []
    for i in range(11, -1, -1):
        month_date = (this_month - timedelta(days=i*30)).replace(day=1)
        month_end = (month_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        payments = Payment.objects.filter(
            month__gte=month_date,
            month__lte=month_end
        )
        
        monthly_data.append({
            'month_name': month_date.strftime('%B %Y'),
            'total_due': payments.aggregate(Sum('amount_due'))['amount_due__sum'] or 0,
            'total_paid': payments.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0,
            'paid_count': payments.filter(status='paid').count(),
            'unpaid_count': payments.filter(status='unpaid').count(),
        })
    
    # Teacher settlements summary
    teacher_stats = []
    for teacher in Teacher.objects.filter(is_active=True):
        groups = Group.objects.filter(teacher=teacher, is_active=True)
        group_ids = list(groups.values_list('group_id', flat=True))
        
        payments = Payment.objects.filter(group_id__in=group_ids)
        total_revenue = payments.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
        
        teacher_stats.append({
            'name': teacher.full_name,
            'groups_count': groups.count(),
            'total_revenue': total_revenue,
            'is_active': teacher.is_active,
        })
    
    context = {
        'monthly_data': json.dumps(monthly_data, ensure_ascii=False, default=str),
        'teacher_stats': teacher_stats,
    }
    
    return render(request, 'reports/financial.html', context)


# ==================== Activity Log ====================

@login_required
def activity_log(request):
    """سجل النشاط - عرض جميع العمليات التي قام بها المستخدمون"""
    from apps.accounts.models import User
    from apps.accounts.decorators import admin_required

    logs = ActivityLog.objects.select_related('user').order_by('-created_at')

    # Filters
    action_filter = request.GET.get('action', '')
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if action_filter:
        logs = logs.filter(action=action_filter)
    if user_filter:
        logs = logs.filter(user_id=user_filter)
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs_page = paginator.get_page(page)

    context = {
        'logs': logs_page,
        'action_choices': ActivityLog.ACTION_CHOICES,
        'users': User.objects.filter(is_active=True).order_by('username'),
        'current_action': action_filter,
        'current_user': user_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'reports/activity_log.html', context)


# ==================== Recycle Bin ====================

@login_required
def recycle_bin(request):
    """
    سلة المهملات - عرض العناصر المحذوفة مع إمكانية الاستعادة أو الحذف النهائي
    """
    filter_type = request.GET.get('type', 'all')
    
    deleted_students = Student.all_objects.dead().select_related('deleted_by')
    deleted_teachers = Teacher.all_objects.dead().select_related('deleted_by')
    deleted_groups = Group.all_objects.dead().select_related('deleted_by')
    deleted_rooms = Room.all_objects.dead().select_related('deleted_by')
    
    context = {
        'deleted_students': deleted_students if filter_type in ('all', 'students') else [],
        'deleted_teachers': deleted_teachers if filter_type in ('all', 'teachers') else [],
        'deleted_groups': deleted_groups if filter_type in ('all', 'groups') else [],
        'deleted_rooms': deleted_rooms if filter_type in ('all', 'rooms') else [],
        'students_count': deleted_students.count(),
        'teachers_count': deleted_teachers.count(),
        'groups_count': deleted_groups.count(),
        'rooms_count': deleted_rooms.count(),
        'total_count': deleted_students.count() + deleted_teachers.count() + deleted_groups.count() + deleted_rooms.count(),
        'current_type': filter_type,
    }
    
    return render(request, 'reports/recycle_bin.html', context)


@login_required
def recycle_restore(request):
    """استعادة عنصر من سلة المهملات"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'})
    
    item_type = request.POST.get('type')
    item_id = request.POST.get('id')
    
    if not item_type or not item_id:
        return JsonResponse({'success': False, 'message': 'بيانات ناقصة'})
    
    model_map = {
        'student': Student,
        'teacher': Teacher,
        'group': Group,
        'room': Room,
    }
    
    model = model_map.get(item_type)
    if not model:
        return JsonResponse({'success': False, 'message': 'نوع غير صالح'})
    
    try:
        obj = model.all_objects.get(pk=item_id)
        obj.restore()
        
        ActivityLog.log(
            user=request.user,
            action='update',
            description=f'استعادة {item_type} من سلة المهملات: {obj}',
            target_model=item_type.capitalize(),
            target_id=item_id,
            request=request
        )
        
        return JsonResponse({
            'success': True,
            'message': f'تم استعادة العنصر بنجاح'
        })
    except model.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'العنصر غير موجود'})


@login_required
def recycle_permanent_delete(request):
    """حذف نهائي من سلة المهملات"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'})
    
    item_type = request.POST.get('type')
    item_id = request.POST.get('id')
    
    if not item_type or not item_id:
        return JsonResponse({'success': False, 'message': 'بيانات ناقصة'})
    
    model_map = {
        'student': Student,
        'teacher': Teacher,
        'group': Group,
        'room': Room,
    }
    
    model = model_map.get(item_type)
    if not model:
        return JsonResponse({'success': False, 'message': 'نوع غير صالح'})
    
    try:
        obj = model.all_objects.get(pk=item_id)
        if not obj.is_deleted:
            return JsonResponse({'success': False, 'message': 'لا يمكن حذف عنصر غير موجود في سلة المهملات'})
        
        obj_name = str(obj)
        # Use Django's actual delete, bypassing soft delete
        models.Model.delete(obj)
        
        ActivityLog.log(
            user=request.user,
            action='delete',
            description=f'حذف نهائي {item_type}: {obj_name}',
            target_model=item_type.capitalize(),
            target_id=item_id,
            request=request
        )
        
        return JsonResponse({
            'success': True,
            'message': f'تم الحذف النهائي بنجاح'
        })
    except model.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'العنصر غير موجود'})


@login_required
def recycle_empty(request):
    """تفريغ سلة المهملات بالكامل"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'})
    
    count = 0
    for model in [Student, Teacher, Group, Room]:
        deleted_qs = model.all_objects.dead()
        count += deleted_qs.count()
        # Use the queryset hard_delete method
        deleted_qs.hard_delete()
    
    ActivityLog.log(
        user=request.user,
        action='delete',
        description=f'تفريغ سلة المهملات: {count} عنصر',
        target_model='RecycleBin',
        target_id=0,
        request=request
    )
    
    messages.success(request, f'تم تفريغ سلة المهملات ({count} عنصر)')
    return redirect('reports:recycle_bin')
