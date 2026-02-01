"""
Notification Views
Parent preferences and notification management
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from .models import NotificationLog, NotificationTemplate, NotificationPreference, NotificationCost
from .services import NotificationCost as NotificationCostService


@login_required
def notification_preferences(request, student_id):
    """
    Manage notification preferences for a student (opt-out mechanism)
    
    Parents can disable specific notification types:
    - attendance_success: Can be disabled
    - payment_reminder: Can be disabled
    - payment_confirmation: Can be disabled
    - late_block: CANNOT be disabled (mandatory)
    - financial_block: CANNOT be disabled (mandatory)
    """
    from apps.students.models import Student
    
    student = get_object_or_404(Student, student_id=student_id)
    
    # Get or create preferences
    preferences, created = NotificationPreference.objects.get_or_create(
        student=student
    )
    
    if request.method == 'POST':
        # Update optional preferences only
        preferences.attendance_success_enabled = request.POST.get('attendance_success_enabled', 'off') == 'on'
        preferences.payment_reminder_enabled = request.POST.get('payment_reminder_enabled', 'off') == 'on'
        preferences.payment_confirmation_enabled = request.POST.get('payment_confirmation_enabled', 'off') == 'on'
        preferences.save()
        
        messages.success(request, 'تم تحديث تفضيلات الإشعارات بنجاح')
        return redirect('students:detail', student_id=student_id)
    
    context = {
        'student': student,
        'preferences': preferences,
        'page_title': 'تفضيلات الإشعارات',
    }
    
    return render(request, 'notifications/preferences.html', context)


@login_required
def notification_history(request, student_id=None):
    """
    View notification history for a student or all students
    """
    from apps.students.models import Student
    
    # Filter by student if provided
    if student_id:
        student = get_object_or_404(Student, student_id=student_id)
        logs = NotificationLog.objects.filter(student=student)
    else:
        student = None
        logs = NotificationLog.objects.all()
    
    # Apply filters
    notification_type = request.GET.get('type')
    status = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if notification_type:
        logs = logs.filter(notification_type=notification_type)
    if status:
        logs = logs.filter(status=status)
    if date_from:
        logs = logs.filter(sent_at__gte=date_from)
    if date_to:
        logs = logs.filter(sent_at__lte=date_to)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'student': student,
        'logs': page_obj,
        'notification_types': NotificationLog.NOTIFICATION_TYPES,
        'status_choices': NotificationLog.STATUS_CHOICES,
        'current_filters': {
            'type': notification_type,
            'status': status,
            'date_from': date_from,
            'date_to': date_to,
        },
        'page_title': 'سجل الإشعارات',
    }
    
    return render(request, 'notifications/history.html', context)


@login_required
def notification_stats(request):
    """
    Dashboard for notification statistics and cost tracking
    """
    from django.db.models import Sum, Count
    
    # Get current month stats
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Monthly stats
    monthly_logs = NotificationLog.objects.filter(
        sent_at__gte=month_start
    )
    
    stats = {
        'total_sent': monthly_logs.filter(status__in=['sent', 'delivered']).count(),
        'total_failed': monthly_logs.filter(status='failed').count(),
        'by_type': {},
        'by_status': {},
    }
    
    # Breakdown by type
    for type_code, type_name in NotificationLog.NOTIFICATION_TYPES:
        count = monthly_logs.filter(notification_type=type_code).count()
        stats['by_type'][type_code] = {
            'name': type_name,
            'count': count,
        }
    
    # Breakdown by status
    for status_code, status_name in NotificationLog.STATUS_CHOICES:
        count = monthly_logs.filter(status=status_code).count()
        stats['by_status'][status_code] = {
            'name': status_name,
            'count': count,
        }
    
    # Cost report
    cost_report = NotificationCostService.get_monthly_report(now.year, now.month)
    stats['cost'] = cost_report
    
    # Recent failed notifications
    recent_failed = NotificationLog.objects.filter(
        status='failed',
        sent_at__gte=now - timedelta(days=7)
    ).select_related('student').order_by('-sent_at')[:20]
    
    # Rate limit warnings
    rate_limit_warnings = NotificationPreference.objects.filter(
        messages_last_hour__gte=4
    ).select_related('student')
    
    context = {
        'stats': stats,
        'recent_failed': recent_failed,
        'rate_limit_warnings': rate_limit_warnings,
        'page_title': 'إحصائيات الإشعارات',
    }
    
    return render(request, 'notifications/stats.html', context)


@login_required
def template_list(request):
    """
    List and manage notification templates
    """
    templates = NotificationTemplate.objects.filter(is_active=True).order_by('template_type')
    
    context = {
        'templates': templates,
        'page_title': 'قوالب الإشعارات',
    }
    
    return render(request, 'notifications/templates.html', context)


@login_required
def template_preview(request, template_id):
    """
    Preview a notification template with sample data
    """
    template = get_object_or_404(NotificationTemplate, id=template_id)
    
    # Sample context for preview
    sample_context = {
        'student_name': 'أحمد محمد علي',
        'group_name': 'مجموعة الرياضيات - المستوى المتقدم',
        'scan_time': '10:00',
        'scheduled_time': '10:00',
        'minutes_late': 5,
        'unpaid_sessions': 2,
        'due_amount': 500,
        'amount': 1000,
        'receipt_number': 'PAY-20240115-12345',
        'payment_date': '2024-01-15',
    }
    
    rendered = template.render(sample_context)
    
    context = {
        'template': template,
        'rendered': rendered,
        'sample_context': sample_context,
        'page_title': f'معاينة قالب: {template.template_name}',
    }
    
    return render(request, 'notifications/template_preview.html', context)


@login_required
def cost_report(request):
    """
    Monthly cost report for notifications
    """
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    
    report = NotificationCostService.get_monthly_report(year, month)
    
    # Get all months for navigation
    costs = NotificationCost.objects.all().order_by('-month')[:12]
    
    context = {
        'report': report,
        'costs': costs,
        'selected_year': year,
        'selected_month': month,
        'page_title': f'تقرير تكاليف الإشعارات - {year}/{month}',
    }
    
    return render(request, 'notifications/cost_report.html', context)


# ========================================
# API Endpoints
# ========================================

@login_required
def api_update_preference(request):
    """
    API endpoint to update a single preference (for AJAX)
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    student_id = request.POST.get('student_id')
    preference_type = request.POST.get('preference_type')
    value = request.POST.get('value') == 'true'
    
    # Validate preference type
    valid_preferences = [
        'attendance_success_enabled',
        'payment_reminder_enabled',
        'payment_confirmation_enabled'
    ]
    
    if preference_type not in valid_preferences:
        return JsonResponse({
            'success': False,
            'error': 'Invalid preference type or cannot be modified'
        }, status=400)
    
    try:
        preference = NotificationPreference.objects.get(student_id=student_id)
        setattr(preference, preference_type, value)
        preference.save()
        
        return JsonResponse({'success': True})
    
    except NotificationPreference.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Preference not found'}, status=404)


@login_required
def api_notification_stats(request):
    """
    API endpoint for notification statistics (for dashboard widgets)
    """
    from django.db.models import Count, Q
    
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get stats
    total_sent = NotificationLog.objects.filter(
        sent_at__gte=month_start,
        status__in=['sent', 'delivered']
    ).count()
    
    total_failed = NotificationLog.objects.filter(
        sent_at__gte=month_start,
        status='failed'
    ).count()
    
    # Get by type
    by_type = {}
    for type_code, type_name in NotificationLog.NOTIFICATION_TYPES:
        count = NotificationLog.objects.filter(
            sent_at__gte=month_start,
            notification_type=type_code
        ).count()
        by_type[type_code] = count
    
    return JsonResponse({
        'total_sent': total_sent,
        'total_failed': total_failed,
        'by_type': by_type,
        'month': now.strftime('%Y-%m'),
    })


# ========================================
# Test View (Development Only)
# ========================================

@login_required
def test_whatsapp(request):
    """
    Test WhatsApp sending (for development only).
    """
    if request.method == 'POST':
        phone = request.POST.get('phone')
        message = request.POST.get('message')
        
        from .services import WhatsAppService
        whatsapp_service = WhatsAppService()
        result = whatsapp_service.send_message(phone, message)
        
        return JsonResponse(result)
    
    return render(request, 'notifications/test.html')
