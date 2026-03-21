from celery import shared_task
from datetime import datetime, timedelta
from django.utils import timezone
from .services import NotificationService
from apps.attendance.models import Session, Attendance
from apps.students.models import StudentGroupEnrollment


@shared_task
def send_attendance_notifications_task():
    """
    مهمة تعمل كل دقيقة للتحقق من الحصص التي انتهت قبل 10 دقائق
    """
    notification_service = NotificationService()
    now = timezone.now()

    # البحث عن الحصص التي تحتاج إشعارات
    sessions = Session.objects.filter(
        session_date=now.date(),
        notification_sent=False,
        is_cancelled=False,
        group__is_active=True,
    ).select_related('group')

    for session in sessions:
        # تحويل وقت الحصة إلى datetime
        session_start = timezone.make_aware(
            datetime.combine(session.session_date, session.group.schedule_time)
        )

        # التحقق من مرور 10 دقائق
        if now >= session_start + timedelta(minutes=10):
            # Get all enrolled students
            enrollments = StudentGroupEnrollment.objects.filter(
                group=session.group,
                is_active=True,
            ).select_related('student')

            for enrollment in enrollments:
                student = enrollment.student
                attendance = Attendance.objects.filter(
                    student=student, session=session
                ).first()

                if attendance:
                    status = attendance.status
                    scan_time = attendance.scan_time or now
                else:
                    status = 'absent'
                    scan_time = now

                if student.parent_phone:
                    notification_service.send_attendance_notification(
                        student.full_name,
                        student.parent_phone,
                        status,
                        scan_time,
                    )

            session.notification_sent = True
            session.save()


@shared_task
def send_monthly_reminders_task():
    """
    مهمة شهرية ترسل تذكيرات المصروفات
    """
    notification_service = NotificationService()
    notification_service.send_monthly_reminders()
