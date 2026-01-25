from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from apps.students.models import Student
from apps.teachers.models import Teacher, Group
from apps.attendance.models import Attendance, Session
from apps.payments.models import Payment
from apps.payments.services import SettlementService


@login_required
def dashboard(request):
    """
    Main dashboard view.
    """
    from datetime import timedelta
    from django.db.models import Sum, Count

    today = timezone.now().date()
    this_month = today.replace(day=1)

    # Get statistics
    total_students = Student.objects.filter(is_active=True).count()
    total_teachers = Teacher.objects.filter(is_active=True).count()
    total_groups = Group.objects.filter(is_active=True).count()

    # Today's attendance
    today_attendances = Attendance.objects.filter(
        session__session_date=today
    ).count()

    # This month payments
    month_payments = Payment.objects.filter(
        month__gte=this_month
    ).aggregate(
        total_due=Sum('amount_due'),
        total_paid=Sum('amount_paid')
    )

    # Recent attendance records
    recent_attendances = Attendance.objects.select_related(
        'student', 'session__group'
    ).order_by('-scan_time')[:10]

    # Pending payments
    pending_payments = Payment.objects.filter(
        status__in=['unpaid', 'partial']
    ).select_related('student', 'group').order_by('-month')[:10]

    # Attendance stats for last 7 days
    week_ago = today - timedelta(days=7)
    week_attendance = Attendance.objects.filter(
        session__session_date__gte=week_ago
    ).values('status').annotate(count=Count('attendance_id'))

    present_count = sum(a['count'] for a in week_attendance if a['status'] == 'present')
    late_count = sum(a['count'] for a in week_attendance if a['status'] == 'late')
    absent_count = sum(a['count'] for a in week_attendance if a['status'] == 'absent')

    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_groups': total_groups,
        'today_attendances': today_attendances,
        'month_total_due': month_payments['total_due'] or 0,
        'month_total_paid': month_payments['total_paid'] or 0,
        'recent_attendances': recent_attendances,
        'pending_payments': pending_payments,
        'present_count': present_count,
        'late_count': late_count,
        'absent_count': absent_count,
    }

    return render(request, 'reports/dashboard.html', context)


@login_required
def attendance_report(request):
    """
    Attendance report view.
    """
    attendances = Attendance.objects.select_related(
        'student', 'session', 'session__group'
    ).order_by('-scan_time')[:100]

    return render(request, 'reports/attendance.html', {
        'attendances': attendances
    })


@login_required
def payment_report(request):
    """
    Payment report view.
    """
    payments = Payment.objects.select_related('student').all()

    return render(request, 'reports/payments.html', {
        'payments': payments
    })
