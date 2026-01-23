from celery import shared_task
from datetime import timedelta
from django.utils import timezone
from .services import NotificationService
from apps.attendance.models import Session


@shared_task
def send_attendance_notifications_task():
    """
    مهمة تعمل كل دقيقة للتحقق من الحصص التي انتهت قبل 15 دقيقة
    """
    notification_service = NotificationService()
    now = timezone.now()
    fifteen_min_ago = now - timedelta(minutes=15)
    
    # البحث عن الحصص التي تحتاج إشعارات
    sessions = Session.objects.filter(
        session_date=now.date(),
        notification_sent=False,
        is_cancelled=False
    ).select_related('group')
    
    for session in sessions:
        # تحويل وقت الحصة إلى datetime
        from datetime import datetime
        session_start = timezone.make_aware(
            datetime.combine(session.session_date, session.group.schedule_time)
        )
        
        # التحقق من مرور 15 دقيقة
        if now >= session_start + timedelta(minutes=15):
            notification_service.send_attendance_notifications(session.session_id)


@shared_task
def send_monthly_reminders_task():
    """
    مهمة شهرية ترسل تذكيرات المصروفات
    """
    notification_service = NotificationService()
    notification_service.send_monthly_reminders()
