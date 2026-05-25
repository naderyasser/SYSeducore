import logging
from datetime import datetime, timedelta, date
from celery import shared_task
from django.utils import timezone
from django.db.models import Count

logger = logging.getLogger('attendance')


@shared_task
def auto_mark_absent_sessions():
    """
    Celery task: runs every 2 minutes.
    Finds sessions that started >= 10 minutes ago and marks any enrolled
    student who does NOT yet have an attendance record as 'absent'.

    This ensures the "10-minute auto-absence" rule is enforced
    without supervisor intervention.
    """
    from apps.attendance.models import Session, Attendance
    from apps.students.models import StudentGroupEnrollment

    now = timezone.now()
    today = now.date()

    sessions = Session.objects.filter(
        session_date=today,
        is_cancelled=False,
        group__is_active=True,
    ).select_related('group')

    count_created = 0

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

        to_create = []
        for enr in enrollments:
            if enr.student_id not in existing_attendance:
                to_create.append(Attendance(
                    student=enr.student,
                    session=session,
                    status='absent',
                    scan_time=now,
                ))

        if to_create:
            Attendance.objects.bulk_create(to_create, ignore_conflicts=True)
            count_created += len(to_create)
            logger.info(
                f"Auto-absence: marked {len(to_create)} students absent "
                f"for session {session.session_id} ({session.group.group_name})"
            )

    return f"Auto-absence: created {count_created} absent records"


@shared_task
def check_billing_cycles():
    """
    Celery task: runs every 6 hours.
    Checks all active enrollments to see if their billing cycle has ended.
    If sessions attended >= sessions_per_cycle, marks the billing_cycle_completed
    flag and prepares the next cycle's Payment record.

    Session-based billing: the cycle is measured by attended + absent sessions,
    not calendar days.
    """
    from apps.attendance.models import Session, Attendance
    from apps.students.models import StudentGroupEnrollment
    from apps.payments.models import Payment

    today = timezone.localtime().date()
    current_month = today.replace(day=1)
    updated = 0

    enrollments = StudentGroupEnrollment.objects.filter(
        is_active=True,
    ).select_related('student', 'group')

    for enr in enrollments:
        group = enr.group
        sessions_per_cycle = enr.sessions_per_cycle or group.sessions_per_month
        if sessions_per_cycle <= 0:
            sessions_per_cycle = group.sessions_per_month or 4

        session_ids = Session.objects.filter(
            group=group,
            session_date__gte=(enr.cycle_start_date or current_month),
            is_cancelled=False,
        ).values_list('pk', flat=True)

        attendance_count = Attendance.objects.filter(
            student=enr.student,
            session_id__in=session_ids,
        ).count()

        if attendance_count >= sessions_per_cycle:
            payment = Payment.objects.filter(
                student=enr.student,
                group=group,
                month=current_month,
            ).first()

            if payment and not payment.billing_cycle_completed:
                payment.billing_cycle_completed = True
                payment.save(update_fields=['billing_cycle_completed'])

                next_month_date = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)
                fee = enr.student.get_monthly_fee_for_group(group)
                if fee > 0:
                    Payment.objects.get_or_create(
                        student=enr.student,
                        group=group,
                        month=next_month_date,
                        defaults={
                            'amount_due': fee,
                            'status': 'unpaid',
                            'sessions_total': sessions_per_cycle,
                        },
                    )
                updated += 1

    return f"Billing cycles checked: {updated} cycles completed, next month payments created"


@shared_task
def send_exception_notification(student_id, group_name, exception_type, reason_display):
    """
    Celery task: send WhatsApp notification when an exception is granted.
    Designed to be called with .delay() after an exception is created.
    """
    from apps.notifications.services import NotificationService
    from apps.students.models import Student

    try:
        student = Student.objects.get(pk=student_id)
    except Student.DoesNotExist:
        return "Student not found"

    notification_service = NotificationService()
    if notification_service.is_disabled:
        return "Notifications disabled, skipping exception notification"

    if exception_type == 'payment':
        message = (
            f"⚠️ *استثناء دفع*\n\n"
            f"تم السماح للطالب *{student.full_name}* بدخول حصة {group_name}\n"
            f"بالرغم من عدم سداد المصروفات.\n"
            f"السبب: {reason_display}\n\n"
            f"_نظام الحضور الآلي_"
        )
    else:
        message = (
            f"⚠️ *استثناء تأخير*\n\n"
            f"تم السماح للطالب *{student.full_name}* بدخول حصة {group_name}\n"
            f"بالرغم من الوصول متأخراً.\n"
            f"السبب: {reason_display}\n\n"
            f"_نظام الحضور الآلي_"
        )

    if student.parent_phone:
        notification_service.whatsapp_service.send_message(student.parent_phone, message)

    return f"Exception notification sent for {student.full_name}"
