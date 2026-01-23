from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.students.models import Student
from apps.attendance.models import Attendance, Session
from apps.payments.models import Payment
from apps.payments.services import SettlementService


@login_required
def dashboard(request):
    """
    Main dashboard view.
    """
    # Get statistics
    total_students = Student.objects.filter(is_active=True).count()
    total_teachers = Student.objects.values('group__teacher').distinct().count()
    total_groups = Student.objects.values('group').distinct().count()
    
    # Today's attendance
    today_attendances = Attendance.objects.filter(
        session__session_date=timezone.now().date()
    ).count()
    
    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_groups': total_groups,
        'today_attendances': today_attendances,
    }
    
    return render(request, 'reports/dashboard.html', context)


@login_required
def attendance_report(request):
    """
    Attendance report view.
    """
    attendances = Attendance.objects.select_related(
        'student', 'student__group', 'session'
    ).order_by('-scan_time')[:100]
    
    return render(request, 'reports/attendance.html', {
        'attendances': attendances
    })


@login_required
def payment_report(request):
    """
    Payment report view.
    """
    payments = Payment.objects.select_related('student', 'student__group').all()
    
    return render(request, 'reports/payments.html', {
        'payments': payments
    })
