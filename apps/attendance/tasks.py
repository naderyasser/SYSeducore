"""
Celery Tasks for Attendance Management
Auto-cancellation and teacher check-in monitoring
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q

logger = get_task_logger(__name__)


@shared_task(name='attendance.check_teacher_attendance')
def check_teacher_attendance_and_auto_cancel():
    """
    Check for sessions where teacher hasn't checked in after 15 minutes.
    Auto-cancel and notify all students.
    
    Runs every 5 minutes via Celery Beat.
    """
    from apps.attendance.models import Session
    from apps.notifications.services import NotificationService
    
    now = timezone.now()
    current_time = now.time()
    current_day = now.strftime('%A')
    
    # Find sessions that:
    # 1. Started more than 15 minutes ago
    # 2. Teacher hasn't checked in
    # 3. Not already cancelled
    # 4. For today
    
    sessions_to_check = Session.objects.filter(
        session_date=now.date(),
        teacher_attended=False,
        is_cancelled=False,
        group__is_active=True
    ).select_related('group', 'group__teacher', 'group__room')
    
    cancelled_count = 0
    notification_service = NotificationService()
    
    for session in sessions_to_check:
        # Calculate time since session start
        session_start_time = session.group.schedule_time
        session_start_datetime = timezone.datetime.combine(now.date(), session_start_time)
        session_start_datetime = timezone.make_aware(session_start_datetime)
        
        time_since_start = now - session_start_datetime
        
        # If more than 15 minutes have passed
        if time_since_start.total_seconds() > (15 * 60):
            # Cancel the session
            session.is_cancelled = True
            session.cancellation_reason = f"المدرس {session.group.teacher.full_name} لم يسجل حضوره بعد 15 دقيقة من بداية الحصة"
            session.save(update_fields=['is_cancelled', 'cancellation_reason'])
            
            logger.warning(
                f"Auto-cancelled session {session.session_id}: "
                f"{session.group.group_name} - Teacher {session.group.teacher.full_name} "
                f"did not check in after 15 minutes"
            )
            
            # Send bulk WhatsApp notifications to all enrolled students
            try:
                enrolled_students = session.group.enrollments.filter(
                    is_active=True
                ).select_related('student')
                
                for enrollment in enrolled_students:
                    student = enrollment.student
                    
                    # Send cancellation notification
                    notification_service.send_session_cancelled(
                        student=student,
                        group=session.group,
                        reason=session.cancellation_reason,
                        session_date=session.session_date
                    )
                
                logger.info(
                    f"Sent cancellation notifications to {enrolled_students.count()} students "
                    f"for session {session.session_id}"
                )
                
            except Exception as e:
                logger.exception(f"Error sending cancellation notifications: {str(e)}")
            
            cancelled_count += 1
    
    if cancelled_count > 0:
        logger.info(f"Auto-cancelled {cancelled_count} sessions due to teacher absence")
    
    return {
        'success': True,
        'cancelled_sessions': cancelled_count,
        'checked_at': now.isoformat()
    }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
)
def send_session_cancelled_notifications(
    self,
    session_id: int
):
    """
    Send session cancelled notifications to all enrolled students.
    Called when admin manually cancels a session.
    
    Args:
        session_id: Session ID
    """
    from apps.attendance.models import Session
    from apps.notifications.services import NotificationService
    
    try:
        session = Session.objects.select_related(
            'group',
            'group__teacher'
        ).get(session_id=session_id)
        
        if not session.is_cancelled:
            logger.warning(f"Session {session_id} is not marked as cancelled")
            return {'success': False, 'error': 'Session not cancelled'}
        
        notification_service = NotificationService()
        enrolled_students = session.group.enrollments.filter(
            is_active=True
        ).select_related('student')
        
        sent_count = 0
        for enrollment in enrolled_students:
            try:
                notification_service.send_session_cancelled(
                    student=enrollment.student,
                    group=session.group,
                    reason=session.cancellation_reason,
                    session_date=session.session_date
                )
                sent_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to send cancellation notification to student "
                    f"{enrollment.student.student_id}: {str(e)}"
                )
        
        logger.info(
            f"Sent {sent_count} cancellation notifications for session {session_id}"
        )
        
        return {
            'success': True,
            'session_id': session_id,
            'notifications_sent': sent_count
        }
        
    except Session.DoesNotExist:
        logger.error(f"Session {session_id} not found")
        return {'success': False, 'error': 'Session not found'}
    except Exception as e:
        logger.exception(f"Error sending session cancellation notifications: {str(e)}")
        raise self.retry(exc=e)
