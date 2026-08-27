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
    from apps.teachers.models import Group
    from apps.teachers.cycles import assign_to_cycle

    now = timezone.now()
    today = timezone.localdate()
    day_name = AttendanceService.get_current_day_name()

    # ── Step 0: materialize today's Session rows once their scheduled start
    # time has passed, even if nobody has scanned. Without this, a group
    # nobody scans in gets no Session row at all, so nobody is ever marked
    # absent and its cycle can never accumulate sessions or close.
    groups_without_session_today = (
        Group.objects.filter(is_active=True, deleted_at__isnull=True)
        .exclude(sessions__session_date=today)
        .prefetch_related('schedules__room')
    )
    for group in groups_without_session_today:
        entry = group.get_schedule_for_day(day_name)
        if entry is None or not entry.start_time:
            continue
        if now < local_datetime(today, entry.start_time):
            continue
        session, created = Session.objects.get_or_create(
            group=group, session_date=today, defaults={'teacher_attended': False},
        )
        if created:
            assign_to_cycle(session)

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


@shared_task
def roll_group_cycles():
    """
    Celery task: runs every 6 hours.

    Session-based billing at the **group** level: every student enrolled in
    a group shares the same cycle and renews together (replaces the old
    per-enrollment ``check_billing_cycles``, which gave each student their
    own independent ``cycle_start_date``/``cycle_end_date`` — the opposite
    of what session-based billing is supposed to mean).

    For every group billed by cycle (``sessions_per_month > 0``):
      * count that group's open cycle's non-cancelled sessions;
      * once they reach ``cycle.sessions_planned``, close the cycle
        (``closed_on`` = the date of the Nth non-cancelled session),
        flag every ``Payment`` on it ``billing_cycle_completed``, and open
        the next cycle at full price for every active, non-exempt
        enrollment that doesn't already have a Payment on it (a package —
        see ``apps.payments.pricing`` — may already have pre-paid it).

    A group's cycle can only close a handful of times per run (weekly
    groups cannot complete two 4-session cycles inside 6 hours), so this
    stays cheap without needing the old task's single-giant-query batching
    — a few queries per group, over ~dozens of groups.
    """
    from apps.teachers.models import Group, GroupCycle
    from apps.teachers.cycles import open_cycle_for
    from apps.students.models import StudentGroupEnrollment
    from apps.payments.models import Payment
    from apps.payments.pricing import base_fee

    closed_count = 0

    groups = (
        Group.objects.filter(is_active=True, deleted_at__isnull=True, sessions_per_month__gt=0)
        .select_related('teacher')
    )

    for group in groups:
        cycle = open_cycle_for(group)
        if cycle.started_on is None:
            continue  # no session has happened in this cycle yet

        counted = cycle.sessions.filter(is_cancelled=False).count()
        if counted < cycle.sessions_planned:
            continue

        closing_session = (
            cycle.sessions.filter(is_cancelled=False)
            .order_by('sequence_in_cycle')[cycle.sessions_planned - 1:cycle.sessions_planned]
            .first()
        )

        with transaction.atomic():
            cycle.closed_on = closing_session.session_date if closing_session else timezone.localdate()
            cycle.save(update_fields=['closed_on'])

            Payment.objects.filter(cycle=cycle, billing_cycle_completed=False).update(
                billing_cycle_completed=True
            )

            next_index = (
                GroupCycle.objects.filter(group=group).order_by('-index')
                .values_list('index', flat=True).first()
            ) or cycle.index
            next_cycle = GroupCycle.objects.create(
                group=group, index=next_index + 1,
                sessions_planned=group.sessions_per_month,
            )

            already_billed = set(
                Payment.objects.filter(cycle=next_cycle).values_list('student_id', flat=True)
            )
            enrollments = (
                StudentGroupEnrollment.objects.filter(group=group, is_active=True)
                .exclude(financial_status='exempt')
                .exclude(student_id__in=already_billed)
                .select_related('student')
            )
            to_create = []
            for enr in enrollments:
                fee = base_fee(enr, group)
                if fee <= 0:
                    continue
                to_create.append(Payment(
                    student=enr.student, group=group, cycle=next_cycle,
                    month=timezone.localdate().replace(day=1),
                    amount_due=fee, status='unpaid',
                    sessions_total=next_cycle.sessions_planned,
                ))
            if to_create:
                Payment.objects.bulk_create(to_create, ignore_conflicts=True)

        closed_count += 1

    return f"Group cycles checked: {closed_count} cycle(s) closed and rolled"


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
