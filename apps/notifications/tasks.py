from celery import shared_task
from datetime import datetime, timedelta
from django.utils import timezone
from .services import NotificationService
from apps.attendance.models import Session, Attendance
from apps.students.models import StudentGroupEnrollment


@shared_task
def send_attendance_notifications_task():
    """
    Celery task: runs every 5 minutes.
    10 minutes after each session starts, auto-marks absent students
    and sends WhatsApp notifications to parents.
    """
    notification_service = NotificationService()
    now = timezone.now()
    today = now.date()

    sessions = Session.objects.filter(
        session_date=today,
        is_cancelled=False,
        group__is_active=True,
    ).select_related('group')

    for session in sessions:
        schedule_time = session.group.schedule_time
        if not schedule_time:
            continue

        session_start = timezone.make_aware(
            datetime.combine(session.session_date, schedule_time)
        )
        trigger_time = session_start + timedelta(minutes=10)

        if now < trigger_time:
            continue

        enrollments = StudentGroupEnrollment.objects.filter(
            group=session.group,
            is_active=True,
        ).select_related('student')

        existing_attendance = set(
            Attendance.objects.filter(session=session).values_list('student_id', flat=True)
        )

        absent_to_create = []
        for enrollment in enrollments:
            student = enrollment.student
            attendance_exists = student.student_id in existing_attendance

            if attendance_exists:
                attendance = Attendance.objects.filter(
                    student=student, session=session
                ).first()
                status = attendance.status if attendance else 'absent'
                scan_time = attendance.scan_time if attendance else now
            else:
                status = 'absent'
                scan_time = now
                absent_to_create.append(Attendance(
                    student=student,
                    session=session,
                    status='absent',
                    scan_time=now,
                ))

            if student.parent_phone:
                notification_service.send_attendance_notification(
                    student.full_name,
                    student.parent_phone,
                    status,
                    scan_time,
                )

        if absent_to_create:
            Attendance.objects.bulk_create(absent_to_create, ignore_conflicts=True)

        if not session.notification_sent:
            session.notification_sent = True
            session.save(update_fields=['notification_sent'])


@shared_task
def send_monthly_reminders_task():
    """
    مهمة شهرية ترسل تذكيرات المصروفات
    """
    notification_service = NotificationService()
    notification_service.send_monthly_reminders()
