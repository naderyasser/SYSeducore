from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from django.core.cache import cache
from apps.students.models import Student
from apps.teachers.models import Teacher, Group
from apps.attendance.models import Attendance, Session
from apps.payments.models import Payment
from apps.notifications.models import NotificationLog
import logging

logger = logging.getLogger(__name__)


@login_required
def stats_api(request):
    """
    API endpoint for dashboard statistics with caching.
    """
    # Check cache first
    cache_key = f'dashboard_stats_{timezone.now().date()}'
    cached_stats = cache.get(cache_key)
    
    if cached_stats:
        return JsonResponse({'stats': cached_stats, 'cached': True})
    
    try:
        today = timezone.now().date()
        this_month = today.replace(day=1)

        # Get statistics with optimized queries
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

        # Pending payments
        pending_payments = Payment.objects.filter(
            status__in=['unpaid', 'partial']
        ).count()

        # Present today
        present_today = Attendance.objects.filter(
            session__session_date=today,
            status='present'
        ).count()

        stats = {
            'total_students': total_students,
            'total_teachers': total_teachers,
            'total_groups': total_groups,
            'today_present': present_today,
            'today_attendances': today_attendances,
            'pending_payments': pending_payments,
            'month_due': float(month_payments['total_due'] or 0),
            'month_paid': float(month_payments['total_paid'] or 0),
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, stats, 300)
        
        return JsonResponse({'stats': stats, 'cached': False})
    
    except Exception as e:
        logger.exception(f"Error generating dashboard stats: {str(e)}")
        return JsonResponse({'error': 'Failed to load statistics'}, status=500)


@login_required
def recent_activity_api(request):
    """
    API endpoint for recent activity on dashboard with error handling.
    """
    try:
        # Recent attendance records with pagination
        limit = min(int(request.GET.get('limit', 10)), 50)  # Max 50
        
        recent_attendances = Attendance.objects.select_related(
            'student', 'session__group'
        ).order_by('-scan_time')[:limit]

        activities = []
        for attendance in recent_attendances:
            try:
                activities.append({
                    'id': attendance.attendance_id,
                    'type': 'attendance',
                    'student_name': attendance.student.full_name,
                    'group_name': attendance.session.group.group_name if attendance.session and attendance.session.group else 'N/A',
                    'status': attendance.status,
                    'time': attendance.scan_time.strftime('%H:%M'),
                    'date': attendance.scan_time.strftime('%Y-%m-%d'),
                })
            except AttributeError as e:
                logger.warning(f"Skipping malformed attendance record {attendance.attendance_id}: {str(e)}")
                continue

        return JsonResponse({'activities': activities})
    
    except Exception as e:
        logger.exception(f"Error fetching recent activities: {str(e)}")
        return JsonResponse({'error': 'Failed to load activities'}, status=500)
