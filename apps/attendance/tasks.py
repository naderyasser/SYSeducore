import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger('attendance')

#: A student who has not scanned this long after a session started is absent.
AUTO_ABSENCE_DELAY_MINUTES = 10


@shared_task
def auto_mark_absent_sessions():
    """
    Celery task: runs every 2 minutes.
    Finds sessions that started >= 10 minutes ago and marks any enrolled
    student who does NOT yet have an attendance record as 'absent'.

    This is the **single** implementation of the 10-minute auto-absence rule.
    ``apps.notifications.tasks`` must only send notifications; it used to mark
    absences too, with slightly different logic, and only
    ``ignore_conflicts=True`` kept the two from raising duplicate-key errors.

    The session's start time comes from ``GroupSchedule`` (via
    ``Group.get_schedule_for_day``), so a group meeting on several days is
    triggered at the right time on each of them instead of always using the
    first day's legacy ``schedule_time``.
    """
    from apps.attendance.models import Session, Attendance
    from apps.attendance.services import AttendanceService, local_datetime
    from apps.students.models import StudentGroupEnrollment

    now = timezone.now()
    today = timezone.localdate()
    day_name = AttendanceService.get_current_day_name()

    sessions = Session.objects.filter(
        session_date=today,
        is_cancelled=False,
        group__is_active=True,
        group__deleted_at__isnull=True,
    ).select_related('group').prefetch_related('group__schedules')

    count_created = 0

    for session in sessions:
        entry = session.group.get_schedule_for_day(day_name)
        if entry is None or not entry.start_time:
            continue

        session_start = local_datetime(session.session_date, entry.start_time)
        trigger_time = session_start + timedelta(minutes=AUTO_ABSENCE_DELAY_MINUTES)

        if now < trigger_time:
            continue

        # Soft-deleted students must not keep generating absence rows.
        enrollments = StudentGroupEnrollment.objects.filter(
            group=session.group,
            is_active=True,
            student__deleted_at__isnull=True,
            student__is_active=True,
        ).select_related('student')

        existing_attendance = set(
            Attendance.objects.filter(session=session).values_list('student_id', flat=True)
        )

        to_create = [
            Attendance(
                student=enr.student,
                session=session,
                status='absent',
                scan_time=now,
            )
            for enr in enrollments
            if enr.student_id not in existing_attendance
        ]

        if not to_create:
            continue

        with transaction.atomic():
            Attendance.objects.bulk_create(to_create, ignore_conflicts=True)
            # bulk_create bypasses update_payment_sessions, so the absences
            # never reached Payment.sessions_attended — yet an absence counts
            # toward the billing cycle exactly like an attended session.
            for attendance in to_create:
                AttendanceService.update_payment_sessions(
                    attendance.student, session.group
                )

        count_created += len(to_create)
        logger.info(
            f"Auto-absence: marked {len(to_create)} students absent "
            f"for session {session.session_id} ({session.group.group_name})"
        )

    return f"Auto-absence: created {count_created} absent records"


def _next_month(month_start):
    """First day of the month after ``month_start``."""
    return (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)


def _projected_cycle_end(cycle_start, sessions_per_cycle, sessions_per_week):
    """
    The date the current cycle is expected to finish.

    ``sessions_per_cycle`` sessions delivered at ``sessions_per_week`` per week
    take ``ceil(sessions_per_cycle / sessions_per_week)`` weeks.
    """
    per_week = max(1, sessions_per_week)
    weeks = -(-sessions_per_cycle // per_week)  # ceil division
    return cycle_start + timedelta(days=weeks * 7 - 1)


@shared_task
def check_billing_cycles():
    """
    Celery task: runs every 6 hours.

    Session-based billing: a cycle is measured by sessions consumed (attended
    **or** absent), not by calendar days. For every active enrollment this
    task:

    * seeds ``cycle_start_date`` / ``cycle_end_date`` the first time it sees
      the enrollment — they used to be read and never written, so they stayed
      ``None`` forever and every cycle silently fell back to the calendar
      month;
    * marks the current month's ``Payment.billing_cycle_completed`` once
      ``sessions_per_cycle`` sessions have been consumed;
    * opens the next month's ``Payment`` row;
    * rolls the enrollment onto the next cycle.

    Everything is batched: a handful of queries in total rather than two or
    more per enrollment.
    """
    from apps.attendance.models import Attendance
    from apps.students.models import StudentGroupEnrollment
    from apps.payments.models import Payment

    today = timezone.localdate()
    current_month = today.replace(day=1)

    enrollments = list(
        StudentGroupEnrollment.objects.filter(is_active=True)
        .select_related('student', 'group')
        .prefetch_related('group__schedules')
    )
    if not enrollments:
        return "Billing cycles checked: 0 cycles completed, next month payments created"

    # ── 1. Seed missing cycle dates ──────────────────────────────────────
    def cycle_size(enr):
        size = enr.sessions_per_cycle or enr.group.sessions_per_month or 0
        return size if size > 0 else 4

    enrollments_to_update = []
    dirty_ids = set()
    for enr in enrollments:
        if enr.cycle_start_date is None:
            enr.cycle_start_date = current_month
            enr.cycle_end_date = None
        if enr.cycle_end_date is None:
            enr.cycle_end_date = _projected_cycle_end(
                enr.cycle_start_date,
                cycle_size(enr),
                len(enr.group.get_schedule_entries()),
            )
            enrollments_to_update.append(enr)
            dirty_ids.add(enr.pk)

    # ── 2. Count consumed sessions per (student, group) in one query ─────
    group_ids = list({enr.group_id for enr in enrollments})
    student_ids = list({enr.student_id for enr in enrollments})
    earliest_cycle_start = min(enr.cycle_start_date for enr in enrollments)

    consumed = {}  # (student_id, group_id) -> [session_date, ...]
    for row in Attendance.objects.filter(
        student_id__in=student_ids,
        session__group_id__in=group_ids,
        session__session_date__gte=earliest_cycle_start,
        session__is_cancelled=False,
    ).values('student_id', 'session__group_id', 'session__session_date'):
        key = (row['student_id'], row['session__group_id'])
        consumed.setdefault(key, []).append(row['session__session_date'])

    # ── 3. Current-month payments in one query ───────────────────────────
    payments = {
        (p.student_id, p.group_id): p
        for p in Payment.objects.filter(
            student_id__in=student_ids,
            group_id__in=group_ids,
            month=current_month,
        )
    }

    next_month_date = _next_month(current_month)
    existing_next_month = {
        (p.student_id, p.group_id)
        for p in Payment.objects.filter(
            student_id__in=student_ids,
            group_id__in=group_ids,
            month=next_month_date,
        )
    }

    # ── 4. Decide, in memory ─────────────────────────────────────────────
    payments_to_update = []
    payments_to_create = []
    updated = 0

    for enr in enrollments:
        sessions_per_cycle = cycle_size(enr)
        dates = sorted(
            d for d in consumed.get((enr.student_id, enr.group_id), [])
            if d >= enr.cycle_start_date
        )
        if len(dates) < sessions_per_cycle:
            continue

        payment = payments.get((enr.student_id, enr.group_id))
        if payment is None or payment.billing_cycle_completed:
            continue

        payment.billing_cycle_completed = True
        payments_to_update.append(payment)

        fee = enr.student.get_monthly_fee_for_group(enr.group)
        key = (enr.student_id, enr.group_id)
        if fee > 0 and key not in existing_next_month:
            existing_next_month.add(key)
            payments_to_create.append(Payment(
                student=enr.student,
                group=enr.group,
                month=next_month_date,
                amount_due=fee,
                status='unpaid',
                sessions_total=sessions_per_cycle,
            ))

        # Roll onto the next cycle: it starts the day after the session that
        # completed this one.
        completed_on = dates[sessions_per_cycle - 1]
        enr.cycle_start_date = completed_on + timedelta(days=1)
        enr.cycle_end_date = _projected_cycle_end(
            enr.cycle_start_date,
            sessions_per_cycle,
            len(enr.group.get_schedule_entries()),
        )
        if enr.pk not in dirty_ids:
            enrollments_to_update.append(enr)
            dirty_ids.add(enr.pk)
        updated += 1

    # ── 5. Write, in bulk ────────────────────────────────────────────────
    with transaction.atomic():
        if payments_to_update:
            Payment.objects.bulk_update(payments_to_update, ['billing_cycle_completed'])
        if payments_to_create:
            Payment.objects.bulk_create(payments_to_create, ignore_conflicts=True)
        if enrollments_to_update:
            StudentGroupEnrollment.objects.bulk_update(
                enrollments_to_update, ['cycle_start_date', 'cycle_end_date']
            )

    return (
        f"Billing cycles checked: {updated} cycles completed, "
        f"next month payments created"
    )


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
