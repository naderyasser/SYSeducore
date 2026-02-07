from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, Count, Q, F, Avg
from django.db.models.functions import TruncDate, TruncMonth
from datetime import timedelta, datetime
from collections import defaultdict
import json

from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room
from apps.attendance.models import Attendance, Session, ActivityLog
from apps.payments.models import Payment


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
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
    week_ago = today - timedelta(days=7)
    current_day_name = AttendanceService_get_day_name()
    
    # ====== OVERALL STATISTICS ======
    total_students = Student.objects.filter(is_active=True).count()
    total_teachers = Teacher.objects.filter(is_active=True).count()
    total_groups = Group.objects.filter(is_active=True).count()
    
    # New students this month
    new_students_this_month = Student.objects.filter(
        is_active=True,
        created_at__date__gte=this_month_start
    ).count()
    
    # ====== ATTENDANCE STATISTICS ======
    # Today's attendance
    today_sessions = Session.objects.filter(session_date=today)
    today_attendances = Attendance.objects.filter(session__session_date=today)
    today_present = today_attendances.filter(status='present').count()
    today_late = today_attendances.filter(status='late').count()
    today_absent = today_attendances.filter(status='absent').count()
    
    # Week attendance trend
    week_attendance_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        day_attendances = Attendance.objects.filter(session__session_date=date)
        week_attendance_data.append({
            'date': date.strftime('%a'),
            'full_date': date.strftime('%Y-%m-%d'),
            'present': day_attendances.filter(status='present').count(),
            'late': day_attendances.filter(status='late').count(),
            'absent': day_attendances.filter(status='absent').count(),
        })
    
    # ====== FINANCIAL STATISTICS ======
    # This month payments
    this_month_payments = Payment.objects.filter(month__gte=this_month_start)
    month_total_due = this_month_payments.aggregate(
        total=Sum('amount_due')
    )['total'] or 0
    month_total_paid = this_month_payments.aggregate(
        total=Sum('amount_paid')
    )['total'] or 0
    month_remaining = month_total_due - month_total_paid
    
    # Payment status counts
    paid_count = this_month_payments.filter(status='paid').count()
    partial_count = this_month_payments.filter(status='partial').count()
    unpaid_count = this_month_payments.filter(status='unpaid').count()
    
    # Monthly revenue trend (last 6 months)
    months_revenue = []
    for i in range(5, -1, -1):
        month_date = (this_month_start - timedelta(days=i*30)).replace(day=1)
        month_end = (month_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        month_data = Payment.objects.filter(
            month__gte=month_date,
            month__lte=month_end
        ).aggregate(
            due=Sum('amount_due'),
            paid=Sum('amount_paid')
        )
        
        months_revenue.append({
            'month': month_date.strftime('%b'),
            'due': float(month_data['due'] or 0),
            'paid': float(month_data['paid'] or 0),
        })
    
    # ====== GROUP STATISTICS ======
    groups_stats = []
    for group in Group.objects.filter(is_active=True).select_related('teacher', 'room')[:5]:
        enrolled_count = StudentGroupEnrollment.objects.filter(
            group=group,
            is_active=True
        ).count()
        
        capacity = group.room.capacity if group.room else 0
        utilization = (enrolled_count / capacity * 100) if capacity > 0 else 0
        
        groups_stats.append({
            'name': group.group_name,
            'teacher': group.teacher.full_name if group.teacher else '-',
            'enrolled': enrolled_count,
            'capacity': capacity,
            'utilization': utilization,
        })
    
    # ====== RECENT ACTIVITY ======
    recent_attendances = Attendance.objects.select_related(
        'student', 'session__group'
    ).order_by('-scan_time')[:8]
    
    recent_payments = Payment.objects.select_related(
        'student', 'group'
    ).filter(
        status__in=['paid', 'partial']
    ).order_by('-payment_date')[:5]
    
    # Pending payments
    pending_payments = Payment.objects.filter(
        status__in=['unpaid', 'partial']
    ).select_related('student', 'group').order_by('-month')[:8]
    
    # ====== TOP PERFORMERS ======
    # Top groups by attendance
    top_groups = Group.objects.filter(is_active=True).annotate(
        attendance_count=Count('sessions__attendances')
    ).order_by('-attendance_count')[:5]

    # ====== SCHEDULE WIDGET (Today's Schedule) ======
    # عرض جدول اليوم: المدرسين + القاعات + المواعيد الحالية
    todays_groups = Group.objects.filter(
        is_active=True,
        schedule_day=current_day_name
    ).select_related('teacher', 'room').order_by('schedule_time')

    today_schedule = []
    for grp in todays_groups:
        enrolled_count = StudentGroupEnrollment.objects.filter(
            group=grp, is_active=True
        ).count()
        today_schedule.append({
            'group': grp,
            'teacher': grp.teacher.full_name,
            'room': grp.room.name if grp.room else '-',
            'time_start': grp.schedule_time.strftime('%I:%M %p'),
            'time_end': grp.get_end_time().strftime('%I:%M %p'),
            'duration': grp.get_duration_display(),
            'enrolled': enrolled_count,
        })

    # ====== ACTIVITY LOG (Who is Active?) ======
    # سجل الدخول - من يعمل على السيستم حالياً
    recent_activities = ActivityLog.objects.select_related('user').order_by('-created_at')[:15]

    context = {
        # Overall stats
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_groups': total_groups,
        'new_students_this_month': new_students_this_month,
        
        # Today's attendance
        'today_sessions': today_sessions.count(),
        'today_present': today_present,
        'today_late': today_late,
        'today_absent': today_absent,
        'today_total': today_present + today_late + today_absent,
        
        # Financial
        'month_total_due': month_total_due,
        'month_total_paid': month_total_paid,
        'month_remaining': month_remaining,
        'collection_rate': (month_total_paid / month_total_due * 100) if month_total_due > 0 else 0,
        'paid_count': paid_count,
        'partial_count': partial_count,
        'unpaid_count': unpaid_count,
        
        # Chart data
        'week_attendance_json': json.dumps(week_attendance_data, ensure_ascii=False),
        'months_revenue_json': json.dumps(months_revenue, ensure_ascii=False),
        
        # Lists
        'groups_stats': groups_stats,
        'recent_attendances': recent_attendances,
        'recent_payments': recent_payments,
        'pending_payments': pending_payments,
        'top_groups': top_groups,

        # Schedule Widget
        'today_schedule': today_schedule,
        'current_day_name': current_day_name,

        # Activity Log
        'recent_activities': recent_activities,
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
        })
    
    context = {
        'monthly_data': json.dumps(monthly_data, ensure_ascii=False, default=str),
        'teacher_stats': teacher_stats,
    }
    
    return render(request, 'reports/financial.html', context)
