"""
Celery Tasks for WhatsApp Notifications
All notification scenarios with async processing and retry logic
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q, Count
from typing import Dict, Any

from .services import NotificationService
from .models import NotificationLog, NotificationCost

logger = get_task_logger(__name__)


# ========================================
# Attendance Notification Tasks
# ========================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    autoretry_for=(Exception,),
)
def send_attendance_success_task(
    self,
    student_id: int,
    group_id: int,
    scan_time_str: str
) -> Dict[str, Any]:
    """
    Send successful attendance notification (async)
    
    Triggered when: Student scans QR, status = present, allow_entry = true
    
    Args:
        student_id: Student ID
        group_id: Group ID
        scan_time_str: Scan time as ISO string
        
    Returns:
        dict: Result
    """
    from apps.students.models import Student
    from apps.teachers.models import Group
    from django.utils.dateparse import parse_datetime
    
    try:
        student = Student.objects.select_related('parent_contact').get(student_id=student_id)
        group = Group.objects.select_related('teacher').get(group_id=group_id)
        scan_time = parse_datetime(scan_time_str)
        
        service = NotificationService()
        result = service.send_attendance_success(student, group, scan_time)
        
        logger.info(f"Attendance success notification sent to {student.full_name}: {result}")
        return result
        
    except Student.DoesNotExist:
        logger.error(f"Student {student_id} not found")
        return {'success': False, 'error': 'Student not found'}
    except Group.DoesNotExist:
        logger.error(f"Group {group_id} not found")
        return {'success': False, 'error': 'Group not found'}
    except Exception as e:
        logger.exception(f"Error sending attendance success notification: {str(e)}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def send_late_block_task(
    self,
    student_id: int,
    group_id: int,
    minutes_late: int,
    scheduled_time: str,
    scan_time: str
) -> Dict[str, Any]:
    """
    Send late block notification (async)
    
    Triggered when: Student scans QR, status = late_blocked, allow_entry = false
    
    Args:
        student_id: Student ID
        group_id: Group ID
        minutes_late: Minutes late
        scheduled_time: Scheduled time
        scan_time: Scan time
        
    Returns:
        dict: Result
    """
    from apps.students.models import Student
    from apps.teachers.models import Group
    
    try:
        student = Student.objects.get(student_id=student_id)
        group = Group.objects.get(group_id=group_id)
        
        service = NotificationService()
        result = service.send_late_block(
            student, group, minutes_late, scheduled_time, scan_time
        )
        
        logger.info(f"Late block notification sent to {student.full_name}: {result}")
        return result
        
    except Student.DoesNotExist:
        logger.error(f"Student {student_id} not found")
        return {'success': False, 'error': 'Student not found'}
    except Group.DoesNotExist:
        logger.error(f"Group {group_id} not found")
        return {'success': False, 'error': 'Group not found'}
    except Exception as e:
        logger.error(f"Error sending late block: {e}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def send_financial_block_new_task(
    self,
    student_id: int,
    group_id: int
) -> Dict[str, Any]:
    """
    Send financial block notification for new student (async)
    
    Triggered when: Student scans QR, is_new_student = true, no payment
    
    Args:
        student_id: Student ID
        group_id: Group ID
        
    Returns:
        dict: Result
    """
    from apps.students.models import Student
    from apps.teachers.models import Group
    
    try:
        student = Student.objects.get(student_id=student_id)
        group = Group.objects.get(group_id=group_id)
        
        service = NotificationService()
        result = service.send_financial_block_new_student(student, group)
        
        logger.info(f"Financial block (new) notification sent to {student.full_name}: {result}")
        return result
        
    except Student.DoesNotExist:
        logger.error(f"Student {student_id} not found")
        return {'success': False, 'error': 'Student not found'}
    except Group.DoesNotExist:
        logger.error(f"Group {group_id} not found")
        return {'success': False, 'error': 'Group not found'}
    except Exception as e:
        logger.error(f"Error sending financial block (new): {e}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def send_financial_block_debt_task(
    self,
    student_id: int,
    group_id: int,
    unpaid_sessions: int,
    due_amount: float
) -> Dict[str, Any]:
    """
    Send financial block notification for debt (async)
    
    Triggered when: Old student, debt > 2 sessions
    
    Args:
        student_id: Student ID
        group_id: Group ID
        unpaid_sessions: Number of unpaid sessions
        due_amount: Amount due
        
    Returns:
        dict: Result
    """
    from apps.students.models import Student
    from apps.teachers.models import Group
    
    try:
        student = Student.objects.get(student_id=student_id)
        group = Group.objects.get(group_id=group_id)
        
        service = NotificationService()
        result = service.send_financial_block_debt(
            student, group, unpaid_sessions, due_amount
        )
        
        logger.info(f"Financial block (debt) notification sent to {student.full_name}: {result}")
        return result
        
    except Student.DoesNotExist:
        logger.error(f"Student {student_id} not found")
        return {'success': False, 'error': 'Student not found'}
    except Group.DoesNotExist:
        logger.error(f"Group {group_id} not found")
        return {'success': False, 'error': 'Group not found'}
    except Exception as e:
        logger.error(f"Error sending financial block (debt): {e}")
        raise self.retry(exc=e)


# ========================================
# Payment Notification Tasks
# ========================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def send_payment_reminder_task(
    self,
    student_id: int,
    group_id: int,
    unpaid_sessions: int,
    due_amount: float
) -> Dict[str, Any]:
    """
    Send payment reminder notification (async)
    
    Triggered by: Celery beat task, daily at 6 PM
    Condition: Student attended 1 unpaid session (warning before block)
    
    Args:
        student_id: Student ID
        group_id: Group ID
        unpaid_sessions: Number of unpaid sessions
        due_amount: Amount due
        
    Returns:
        dict: Result
    """
    from apps.students.models import Student
    from apps.teachers.models import Group
    
    try:
        student = Student.objects.get(student_id=student_id)
        group = Group.objects.get(group_id=group_id)
        
        service = NotificationService()
        result = service.send_payment_reminder(
            student, group, unpaid_sessions, due_amount
        )
        
        logger.info(f"Payment reminder sent to {student.full_name}: {result}")
        return result
        
    except Student.DoesNotExist:
        logger.error(f"Student {student_id} not found")
        return {'success': False, 'error': 'Student not found'}
    except Group.DoesNotExist:
        logger.error(f"Group {group_id} not found")
        return {'success': False, 'error': 'Group not found'}
    except Exception as e:
        logger.error(f"Error sending payment reminder: {e}")
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def send_payment_confirmation_task(
    self,
    student_id: int,
    amount: float,
    receipt_number: str,
    payment_date_str: str
) -> Dict[str, Any]:
    """
    Send payment confirmation notification (async)
    
    Triggered when: Payment is recorded in system
    
    Args:
        student_id: Student ID
        amount: Payment amount
        receipt_number: Receipt number
        payment_date_str: Payment date as ISO string
        
    Returns:
        dict: Result
    """
    from apps.students.models import Student
    from django.utils.dateparse import parse_datetime
    
    try:
        student = Student.objects.get(student_id=student_id)
        payment_date = parse_datetime(payment_date_str)
        
        service = NotificationService()
        result = service.send_payment_confirmation(
            student, amount, receipt_number, payment_date
        )
        
        logger.info(f"Payment confirmation sent to {student.full_name}: {result}")
        return result
        
    except Student.DoesNotExist:
        logger.error(f"Student {student_id} not found")
        return {'success': False, 'error': 'Student not found'}
    except Exception as e:
        logger.error(f"Error sending payment confirmation: {e}")
        raise self.retry(exc=e)


# ========================================
# Scheduled Tasks (Celery Beat)
# ========================================

@shared_task
def daily_payment_reminders_task():
    """
    Daily task to send payment reminders
    Runs at 6 PM every day
    
    Finds students with 1 unpaid session and sends warning
    """
    from apps.students.models import Student, StudentGroupEnrollment
    from apps.teachers.models import Group
    
    logger.info("Starting daily payment reminders task")
    
    # Find enrollments with exactly 1 unpaid session (warning level)
    enrollments = StudentGroupEnrollment.objects.filter(
        is_active=True,
        is_financially_blocked=False
    ).select_related('student', 'group')
    
    reminders_sent = 0
    
    for enrollment in enrollments:
        debt = enrollment.sessions_attended - enrollment.sessions_paid_for
        
        # Send reminder if exactly 1 unpaid session
        if debt == 1:
            # Check if reminder was sent recently (avoid spam)
            recent_reminder = NotificationLog.objects.filter(
                student=enrollment.student,
                notification_type='payment_reminder',
                sent_at__gte=timezone.now() - timedelta(hours=24)
            ).exists()
            
            if not recent_reminder:
                # Get group fee for due amount calculation
                fee = enrollment.get_effective_fee()
                
                send_payment_reminder_task.delay(
                    student_id=enrollment.student.student_id,
                    group_id=enrollment.group.group_id,
                    unpaid_sessions=debt,
                    due_amount=fee
                )
                reminders_sent += 1
    
    logger.info(f"Daily payment reminders task completed: {reminders_sent} reminders queued")
    return {'reminders_sent': reminders_sent}


@shared_task
def retry_failed_notifications_task():
    """
    Retry failed notifications
    Runs every 10 minutes
    """
    logger.info("Starting retry failed notifications task")
    
    # Get notifications that should be retried
    failed_logs = NotificationLog.objects.filter(
        status='failed',
        retry_count__lt=3
    ).select_related('student')
    
    retried = 0
    
    for log in failed_logs:
        if log.can_retry():
            log.schedule_retry()
            
            # Re-send based on notification type
            if log.notification_type == 'attendance_success':
                # This would need more context to retry properly
                pass
            elif log.notification_type == 'late_block':
                pass
            # Add other types as needed
            
            retried += 1
    
    logger.info(f"Retry task completed: {retried} notifications scheduled for retry")
    return {'retried': retried}


@shared_task
def check_notification_costs_task():
    """
    Check monthly notification costs and alert if budget exceeded
    Runs daily at midnight
    """
    from django.conf import settings
    
    logger.info("Checking notification costs")
    
    now = timezone.now()
    monthly_budget = getattr(settings, 'WHATSAPP_MONTHLY_BUDGET', 500)  # Default 500 EGP
    
    cost_record = NotificationCost.get_monthly_cost(now.year, now.month)
    
    if cost_record and cost_record.total_cost > monthly_budget:
        logger.warning(
            f"WhatsApp budget exceeded! "
            f"Cost: {cost_record.total_cost} EGP, Budget: {monthly_budget} EGP"
        )
        
        # TODO: Send alert to admin
        # Could send email or admin notification
    
    return {
        'month': f"{now.year}-{now.month}",
        'total_cost': float(cost_record.total_cost) if cost_record else 0,
        'budget': monthly_budget,
        'exceeded': (cost_record.total_cost > monthly_budget) if cost_record else False
    }


@shared_task
def cleanup_old_notification_logs_task():
    """
    Clean up old notification logs (older than 6 months)
    Runs weekly
    """
    from django.utils import timezone
    
    logger.info("Cleaning up old notification logs")
    
    six_months_ago = timezone.now() - timedelta(days=180)
    
    deleted_count = NotificationLog.objects.filter(
        created_at__lt=six_months_ago
    ).delete()[0]
    
    logger.info(f"Deleted {deleted_count} old notification logs")
    return {'deleted_count': deleted_count}


# ========================================
# Batch Notification Tasks
# ========================================

@shared_task
def send_batch_payment_reminders_task(student_ids: list, group_id: int):
    """
    Send payment reminders to multiple students at once
    Useful for bulk reminders
    
    Args:
        student_ids: List of student IDs
        group_id: Group ID
    """
    from apps.students.models import Student, StudentGroupEnrollment
    from apps.teachers.models import Group
    
    group = Group.objects.get(group_id=group_id)
    results = []
    
    for student_id in student_ids:
        try:
            enrollment = StudentGroupEnrollment.objects.get(
                student_id=student_id,
                group_id=group_id
            )
            
            debt = enrollment.sessions_attended - enrollment.sessions_paid_for
            fee = enrollment.get_effective_fee()
            
            result = send_payment_reminder_task.delay(
                student_id=student_id,
                group_id=group_id,
                unpaid_sessions=debt,
                due_amount=fee
            )
            
            results.append({
                'student_id': student_id,
                'task_id': result.id
            })
            
        except StudentGroupEnrollment.DoesNotExist:
            logger.warning(f"Enrollment not found for student {student_id} in group {group_id}")
    
    return {'results': results}


# ========================================
# Helper Functions
# ========================================

def trigger_attendance_notification(
    student_id: int,
    group_id: int,
    scan_time: timezone.datetime,
    status: str,
    **kwargs
) -> None:
    """
    Trigger appropriate notification based on attendance status
    
    This is called from AttendanceService after processing a scan
    
    Args:
        student_id: Student ID
        group_id: Group ID
        scan_time: Scan timestamp
        status: Attendance status (present, late_blocked, etc.)
        **kwargs: Additional context
    """
    if status == 'present':
        send_attendance_success_task.delay(
            student_id=student_id,
            group_id=group_id,
            scan_time_str=scan_time.isoformat()
        )
    
    elif status == 'late_blocked':
        send_late_block_task.delay(
            student_id=student_id,
            group_id=group_id,
            minutes_late=kwargs.get('minutes_late', 0),
            scheduled_time=kwargs.get('scheduled_time', ''),
            scan_time=scan_time.strftime('%H:%M')
        )
    
    elif status == 'blocked_payment_new':
        send_financial_block_new_task.delay(
            student_id=student_id,
            group_id=group_id
        )
    
    elif status == 'blocked_payment_debt':
        send_financial_block_debt_task.delay(
            student_id=student_id,
            group_id=group_id,
            unpaid_sessions=kwargs.get('unpaid_sessions', 0),
            due_amount=kwargs.get('due_amount', 0)
        )


def trigger_payment_confirmation(
    student_id: int,
    amount: float,
    receipt_number: str,
    payment_date: timezone.datetime
) -> None:
    """
    Trigger payment confirmation notification
    
    Args:
        student_id: Student ID
        amount: Payment amount
        receipt_number: Receipt number
        payment_date: Payment date
    """
    send_payment_confirmation_task.delay(
        student_id=student_id,
        amount=amount,
        receipt_number=receipt_number,
        payment_date_str=payment_date.isoformat()
    )
