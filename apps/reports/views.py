from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.paginator import Paginator
from apps.students.models import Student
from apps.teachers.models import Teacher, Group
from apps.attendance.models import Attendance, Session
from apps.payments.models import Payment
from apps.payments.services import SettlementService
from apps.notifications.models import NotificationLog


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

    # Recent notifications
    recent_notifications = NotificationLog.objects.select_related('student').order_by('-sent_at')[:10]

    # Notification stats
    today_notifications = NotificationLog.objects.filter(sent_at__date=today).count()
    failed_notifications = NotificationLog.objects.filter(status='failed', sent_at__date=today).count()

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
        'recent_notifications': recent_notifications,
        'today_notifications': today_notifications,
        'failed_notifications': failed_notifications,
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


@login_required
def notifications_list(request):
    """
    List all notifications with filtering and pagination.
    """
    notifications = NotificationLog.objects.select_related('student').order_by('-sent_at')

    # Filter by notification type
    notification_type = request.GET.get('type')
    if notification_type:
        notifications = notifications.filter(notification_type=notification_type)

    # Filter by status
    status = request.GET.get('status')
    if status:
        notifications = notifications.filter(status=status)

    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        notifications = notifications.filter(sent_at__date__gte=date_from)
    if date_to:
        notifications = notifications.filter(sent_at__date__lte=date_to)

    # Search by student name
    search = request.GET.get('search')
    if search:
        notifications = notifications.filter(student_name__icontains=search)

    # Pagination
    paginator = Paginator(notifications, 25)
    page = request.GET.get('page')
    notifications_page = paginator.get_page(page)

    # Get stats
    total_sent = NotificationLog.objects.filter(status='sent').count()
    total_failed = NotificationLog.objects.filter(status='failed').count()

    context = {
        'notifications': notifications_page,
        'notification_types': NotificationLog.NOTIFICATION_TYPES,
        'total_sent': total_sent,
        'total_failed': total_failed,
        'selected_type': notification_type,
        'selected_status': status,
        'date_from': date_from,
        'date_to': date_to,
        'search': search,
    }

    return render(request, 'reports/notifications.html', context)
