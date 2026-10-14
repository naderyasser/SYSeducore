"""
Celery tasks for the notifications app.

This module **only sends notifications**. It used to also auto-create the
``absent`` attendance rows, duplicating ``apps.attendance.tasks`` with slightly
different logic on a different schedule (DATA-18); the attendance app owns that
rule now and these tasks simply read whatever attendance state exists.

Every automated send is idempotent: a ``WhatsAppMessage`` row carrying a unique
``dedup_key`` is *reserved* before the API call, so a retried task, an
overlapping beat tick or a worker that died mid-loop can never deliver — and
never pay for — the same message twice (BUG-05).
"""
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import WhatsAppMessage
from .services import NotificationService

logger = logging.getLogger('notifications')

#: A session's parents are notified this long after the session started — the
#: same delay ``apps.attendance.tasks.AUTO_ABSENCE_DELAY_MINUTES`` uses to mark
#: the non-scanners absent, so the message reflects the final roster.
NOTIFICATION_DELAY_MINUTES = 10

#: ``date.weekday()`` -> the English day names stored on ``GroupSchedule``.
_WEEKDAY_NAMES = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
]


def _local_datetime(day, clock_time):
    """Combine a date and a naive time into an aware **local** datetime."""
    return datetime.combine(day, clock_time, tzinfo=timezone.get_current_timezone())


def _session_start_time(session):
    """
    The local start time of *session*, or ``None`` when the group has none.

    Prefers the ``GroupSchedule`` entry for the session's own weekday (a group
    that meets Saturday 16:00 and Tuesday 18:00 must be triggered at the right
    hour on each day) and falls back to the legacy ``Group.schedule_time`` for
    groups that have no schedule rows yet.
    """
    group = session.group
    day_name = _WEEKDAY_NAMES[session.session_date.weekday()]

    entry = None
    get_for_day = getattr(group, 'get_schedule_for_day', None)
    if get_for_day is not None:
        entry = get_for_day(day_name)
    if entry is not None and entry.start_time:
        return entry.start_time

    return group.schedule_time


def _reserve_message(dedup_key, **fields):
    """
    Reserve the right to send one message, or return ``None``.

    The unique ``dedup_key`` is the whole point: the row is inserted **before**
    the HTTP call, so two workers racing on the same (session, student) — or
    the same task running again five minutes later — cannot both send. The
    insert is wrapped in its own ``atomic`` block so the ``IntegrityError``
    does not poison the caller's transaction.
    """
    try:
        with transaction.atomic():
            return WhatsAppMessage.objects.create(dedup_key=dedup_key, **fields)
    except IntegrityError:
        return None


def _finalize_message(record, result):
    """Record the outcome of a send on its reserved ``WhatsAppMessage`` row."""
    succeeded = bool(result.get('success'))
    record.status = 'sent' if succeeded else 'failed'
    record.sent_at = timezone.now() if succeeded else None
    record.error_message = result.get('error', '') or ''
    record.save(update_fields=['status', 'sent_at', 'error_message', 'updated_at'])
    return succeeded


def notice_status(attendance):
    """What the parent is told for ``attendance`` (``None`` = no record yet,
    reported as absent). A desk-typed «عذر» — ``exception`` with no
    ExceptionRecord — is an excused *absence*, not a late arrival."""
    if attendance is None:
        return 'absent'
    if attendance.status == 'exception' and attendance.exception_record_id is None:
        return 'excused'
    return attendance.status


def _told(message_text):
    """Which of absent / excused / came a sent attendance message announced."""
    if 'تنبيه غياب' in message_text:
        return 'absent'
    if 'غياب بعذر' in message_text:
        return 'excused'
    return 'came'


#: Corrections are only sent while the parent can still act on them — a desk
#: fixing last month's sheet must not wake every parent up with old news.
CORRECTION_MAX_AGE_DAYS = 1


@shared_task
def send_attendance_correction(session_id, student_id):
    """
    Tell the parent when a record changed after they were already notified:
    the 10-minute message said «غياب» and the student scanned in at minute 15
    (or the desk fixed the sheet), or the other way round.

    Compares what the last delivered message for this (session, student)
    announced with the record as it stands now and sends a correction only
    when the two disagree, so flipping a status back and forth costs at most
    one message per real change. Nothing is sent when no message went out
    yet: ``send_attendance_notifications_task`` reads the live record and
    will send the right one itself.
    """
    from apps.attendance.models import Attendance, Session
    from apps.students.models import Student

    notification_service = NotificationService()
    if notification_service.is_disabled:
        return 'Notifications disabled'

    session = Session.objects.select_related('group').filter(pk=session_id).first()
    student = Student.objects.filter(pk=student_id).first()
    if session is None or student is None:
        return 'Missing session or student'
    if session.session_date < timezone.localdate() - timedelta(days=CORRECTION_MAX_AGE_DAYS):
        return 'Too old to correct'

    prefix = f'attendance:{session_id}:{student_id}'
    fix_prefix = f'attendance-fix:{session_id}:{student_id}:'
    history = list(WhatsAppMessage.objects.filter(
        Q(dedup_key=prefix) | Q(dedup_key__startswith=fix_prefix)
    ))
    delivered = sorted(
        (m for m in history if m.status in ('pending', 'sent', 'delivered')),
        key=lambda m: m.created_at,
    )
    if not delivered:
        return 'Nothing sent yet'

    attendance = Attendance.objects.filter(session_id=session_id, student_id=student_id).first()
    if attendance is None:
        # A cleared record means "unknown", not "absent" — a desk undoing a
        # wrong mark must not send the family an absence notice.
        return 'No record'
    status = notice_status(attendance)
    now_kind = 'came' if status in ('present', 'late', 'exception') else status
    if _told(delivered[-1].message_text) == now_kind:
        return 'Already consistent'

    phone = (student.parent_phone or '').strip()
    if not phone:
        return 'No parent phone'

    record = _reserve_message(
        f'{fix_prefix}{len(history)}',
        phone_number=phone[:20],
        message_text=notification_service.whatsapp_service.build_attendance_correction(
            student.full_name, status, attendance.scan_time,
        ),
        message_type='attendance',
        student=student,
        group=session.group,
        status='pending',
    )
    if record is None:
        return 'Already handled'
    try:
        result = notification_service.send_text(phone, record.message_text, idempotency_key=record.dedup_key)
    except Exception:
        logger.exception('Attendance correction failed for student %s (session %s)', student_id, session_id)
        result = {'success': False, 'error': 'خطأ غير متوقع أثناء الإرسال'}
    return 'Correction sent' if _finalize_message(record, result) else 'Correction failed'


def queue_attendance_correction(session_id, student_id):
    """Queue :func:`send_attendance_correction` once the caller's transaction
    commits (the task must see the new status). Never raises: a broker
    outage must not fail the scan or the sheet edit that triggered it."""
    def _send():
        try:
            send_attendance_correction.delay(session_id, student_id)
        except Exception:
            logger.warning('Could not queue attendance correction for student %s (session %s)',
                           student_id, session_id, exc_info=True)
    transaction.on_commit(_send)


@shared_task
def send_attendance_notifications_task():
    """
    Celery task: runs every 5 minutes.

    ``NOTIFICATION_DELAY_MINUTES`` after a session starts, sends each parent a
    WhatsApp message describing what the attendance record says about their
    child (present / late / absent). It **creates no attendance rows** —
    ``apps.attendance.tasks.auto_mark_absent_sessions`` owns that (DATA-18);
    a student with no record yet is simply reported as absent.

    Idempotency (BUG-05 — this task used to re-send every message every five
    minutes until midnight, roughly 96 duplicates per parent per session at
    full API cost):

    * the queryset now filters ``notification_sent=False``, the flag that was
      written and never read;
    * the flag is only raised once the whole roster has been processed, so a
      worker killed mid-loop resumes on the next tick;
    * each (session, student) pair reserves a unique ``WhatsAppMessage`` row
      before the API call, so resuming re-sends nothing that already went out.

    A reserved pair is never retried, even if the API call failed: at-most-once
    delivery is the deliberate trade-off — a duplicate WhatsApp costs money and
    annoys a parent, a missed one is visible in the message history.
    """
    from apps.attendance.models import Attendance, Session
    from apps.students.models import StudentGroupEnrollment

    notification_service = NotificationService()
    if notification_service.is_disabled:
        logger.info('Attendance notifications skipped: notifications are disabled')
        return 'Notifications disabled'

    now = timezone.now()
    today = timezone.localdate()  # TZ-04: the UTC date is yesterday until 02:00 Cairo

    sessions = (
        Session.objects.filter(
            session_date=today,
            is_cancelled=False,
            group__is_active=True,
            group__deleted_at__isnull=True,
            notification_sent=False,  # BUG-05: the flag is finally read
        )
        .select_related('group')
        .prefetch_related('group__schedules')
    )

    sent_count = 0
    failed_count = 0

    for session in sessions:
        start_time = _session_start_time(session)
        if not start_time:
            continue

        trigger_time = (
            _local_datetime(session.session_date, start_time)
            + timedelta(minutes=NOTIFICATION_DELAY_MINUTES)
        )
        if now < trigger_time:
            continue

        # Soft-deleted / deactivated students must not generate messages.
        enrollments = StudentGroupEnrollment.objects.filter(
            group=session.group,
            is_active=True,
            student__deleted_at__isnull=True,
            student__is_active=True,
        ).select_related('student')

        attendance_by_student = {
            attendance.student_id: attendance
            for attendance in Attendance.objects.filter(session=session)
        }

        completed = True
        for enrollment in enrollments:
            student = enrollment.student
            phone = (student.parent_phone or '').strip()
            if not phone:
                continue

            attendance = attendance_by_student.get(student.pk)
            status = notice_status(attendance)
            scan_time = attendance.scan_time if attendance else now

            record = _reserve_message(
                f'attendance:{session.pk}:{student.pk}',
                phone_number=phone[:20],
                message_text=notification_service.whatsapp_service
                .build_attendance_message(student.full_name, status, scan_time),
                message_type='attendance',
                student=student,
                group=session.group,
                status='pending',
            )
            if record is None:
                # Already handled by an earlier run or a concurrent worker.
                continue

            try:
                result = notification_service.send_text(
                    phone, record.message_text, idempotency_key=record.dedup_key
                )
            except Exception:  # never let one parent break the whole roster
                logger.exception(
                    'Attendance notification failed for student %s (session %s)',
                    student.pk, session.pk,
                )
                result = {'success': False, 'error': 'خطأ غير متوقع أثناء الإرسال'}
                completed = False

            if _finalize_message(record, result):
                sent_count += 1
            else:
                failed_count += 1

        if completed:
            session.notification_sent = True
            session.save(update_fields=['notification_sent'])

    return (
        f'Attendance notifications: {sent_count} sent, {failed_count} failed'
    )


@shared_task
def send_monthly_reminders_task():
    """
    مهمة شهرية ترسل تذكيرات المصروفات

    BUG-02: this used to call ``NotificationService.send_monthly_reminders()``,
    a method that did not exist, so the 1st-of-the-month cron raised
    ``AttributeError`` and no reminder was ever delivered.
    """
    summary = NotificationService().send_monthly_reminders()
    return (
        f"Monthly reminders: {summary['sent']} sent, "
        f"{summary['failed']} failed, {summary['skipped']} skipped"
    )


@shared_task
def send_bulk_whatsapp_task(recipients, message, batch_key, sent_by_id=None,
                            group_id=None, message_type='custom'):
    """
    الإرسال الجماعي في الخلفية — PERF-03

    Bulk sending used to run inside the request thread: every message is a
    blocking HTTP call with a 10-second timeout, so 100 students could block a
    gunicorn worker for ~1000 s. Past the 120 s timeout the worker is killed
    mid-loop, leaving the messages half delivered with no record of where it
    stopped.

    Args:
        recipients: ``[{'phone': '01…', 'student_id': 3 | None,
            'message': '…' | None}, …]`` — ``message`` overrides the batch body
            for that recipient (used when the name is woven into the text)
        message: the default message body
        batch_key: a unique id for this batch (``uuid4().hex`` from the caller)
        sent_by_id: the user who requested the send, for the audit trail
        group_id: optional group the batch belongs to
        message_type: ``WhatsAppMessage.MESSAGE_TYPE_CHOICES`` value

    Resumable and idempotent: every recipient reserves
    ``bulk:<batch_key>:<index>`` before its API call, so re-running the task
    (a Celery retry, a manual replay) only sends what has not been sent yet.
    """
    from apps.students.models import Student

    notification_service = NotificationService()
    if notification_service.is_disabled:
        logger.info('Bulk WhatsApp batch %s skipped: notifications disabled', batch_key)
        return 'Notifications disabled'

    valid_types = {value for value, _label in WhatsAppMessage.MESSAGE_TYPE_CHOICES}
    if message_type not in valid_types:
        message_type = 'custom'

    student_ids = [r.get('student_id') for r in recipients if r.get('student_id')]
    students = {
        student.pk: student
        for student in Student.all_objects.filter(pk__in=student_ids)
    }

    sent_count = 0
    failed_count = 0

    for index, recipient in enumerate(recipients):
        phone = str(recipient.get('phone') or '').strip()
        if not phone:
            continue

        body = recipient.get('message') or message

        record = _reserve_message(
            f'bulk:{batch_key}:{index}',
            phone_number=phone[:20],
            message_text=body,
            message_type=message_type,
            student=students.get(recipient.get('student_id')),
            group_id=group_id,
            sent_by_id=sent_by_id,
            status='pending',
        )
        if record is None:
            continue

        try:
            result = notification_service.send_text(
                phone, body, idempotency_key=record.dedup_key
            )
        except Exception:
            logger.exception('Bulk WhatsApp send failed for %s (batch %s)', phone, batch_key)
            result = {'success': False, 'error': 'خطأ غير متوقع أثناء الإرسال'}

        if _finalize_message(record, result):
            sent_count += 1
        else:
            failed_count += 1

    logger.info(
        'Bulk WhatsApp batch %s: %s sent, %s failed', batch_key, sent_count, failed_count
    )
    return f'Bulk WhatsApp: {sent_count} sent, {failed_count} failed'


@shared_task
def send_bulk_attendance_report_task(group_id, session_date=None, batch_key=None,
                                     sent_by_id=None):
    """
    بناء وإرسال تقرير الحضور الجماعي في الخلفية — PERF-03

    ``session_date`` is an ISO ``YYYY-MM-DD`` string (or ``None`` for today);
    Celery only carries JSON, so dates cross the wire as text.
    """
    from apps.teachers.models import Group

    try:
        group = Group.objects.get(pk=group_id)
    except Group.DoesNotExist:
        return 'Group not found'

    report_date = None
    if session_date:
        try:
            report_date = datetime.strptime(session_date, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return 'Invalid session date'

    notification_service = NotificationService()
    try:
        message, recipients = (
            notification_service.whatsapp_service.build_attendance_report(group, report_date)
        )
    except LookupError as exc:
        logger.info('Attendance report for group %s skipped: %s', group_id, exc)
        return str(exc)

    return send_bulk_whatsapp_task(
        recipients=[
            {'phone': r['phone'], 'student_id': r['student'].pk} for r in recipients
        ],
        message=message,
        batch_key=batch_key or f'attendance-report:{group_id}:{report_date or "today"}',
        sent_by_id=sent_by_id,
        group_id=group_id,
        message_type='attendance',
    )


#: How long before a session starts the reminder goes out.
SESSION_REMINDER_LEAD_MINUTES = 60


def notify_session_cancelled(session, reason=''):
    """
    Tell the parents of everyone enrolled that a session is off.

    Called synchronously from the cancel action rather than left to a beat
    tick: a cancellation is only useful if it arrives *before* the family sets
    out, and the desk cancels the lesson minutes before it was due to start.

    Returns (sent, failed). Never raises — a messaging outage must not roll
    back the cancellation itself, which is a bookkeeping fact independent of
    whether anyone was told.
    """
    from apps.students.models import StudentGroupEnrollment

    service = NotificationService()
    group = session.group
    when = session.session_date.strftime('%Y-%m-%d')

    enrollments = (
        StudentGroupEnrollment.objects
        .filter(group=group, is_active=True, student__deleted_at__isnull=True)
        .select_related('student')
    )

    sent = failed = 0
    for enrollment in enrollments:
        student = enrollment.student
        phone = student.parent_phone or student.student_phone
        if not phone:
            continue

        text = (
            f'إلغاء حصة\n'
            f'الطالب: {student.full_name}\n'
            f'المجموعة: {group.group_name}\n'
            f'التاريخ: {when}\n'
        )
        if reason:
            text += f'السبب: {reason}\n'
        text += 'نعتذر عن الإزعاج — سيتم إبلاغكم بموعد التعويض.'

        # One message per (session, student): re-cancelling an already
        # cancelled session, or a double-click on the button, must not send
        # the same apology twice.
        record = _reserve_message(
            f'session-cancelled:{session.pk}:{student.pk}',
            phone_number=phone,
            message_text=text,
            message_type='parent',
            student=student,
            group=group,
            status='pending',
        )
        if record is None:
            continue

        try:
            result = service.send_text(phone, text)
        except Exception:  # noqa: BLE001 - a send failure is not a cancel failure
            logger.exception('session cancellation notice failed (session=%s)', session.pk)
            result = {'success': False, 'error': 'exception'}

        if _finalize_message(record, result):
            sent += 1
        else:
            failed += 1

    return sent, failed


@shared_task
def send_session_reminders_task():
    """
    Remind parents about a session starting within the next hour.

    Complements the cancellation notice: between them the family knows both
    that a lesson is coming and that it is off. Idempotent per (session,
    student) like every other automated send here, so the beat interval can be
    tightened without sending twice.
    """
    from apps.attendance.models import Session
    from apps.students.models import StudentGroupEnrollment

    now = timezone.localtime()
    today = now.date()
    horizon = now + timedelta(minutes=SESSION_REMINDER_LEAD_MINUTES)

    service = NotificationService()
    sent = failed = 0

    sessions = (
        Session.objects
        .filter(session_date=today, is_cancelled=False,
                group__is_active=True, group__deleted_at__isnull=True)
        .select_related('group')
        .prefetch_related('group__schedules')
    )

    for session in sessions:
        # ``_session_start_time`` returns a clock time; combine it with the
        # session's own date before comparing against "now".
        clock = _session_start_time(session)
        if clock is None:
            continue
        start = _local_datetime(session.session_date, clock)
        # Only the window ahead of us: a session that already started is the
        # attendance task's business, not a reminder's.
        if not (now < start <= horizon):
            continue

        enrollments = (
            StudentGroupEnrollment.objects
            .filter(group=session.group, is_active=True,
                    student__deleted_at__isnull=True)
            .select_related('student')
        )
        for enrollment in enrollments:
            student = enrollment.student
            phone = student.parent_phone or student.student_phone
            if not phone:
                continue

            text = (
                f'تذكير بحصة اليوم\n'
                f'الطالب: {student.full_name}\n'
                f'المجموعة: {session.group.group_name}\n'
                f'الموعد: {start.strftime("%I:%M %p")}'
            )
            record = _reserve_message(
                f'session-reminder:{session.pk}:{student.pk}',
                phone_number=phone,
                message_text=text,
                message_type='parent',
                student=student,
                group=session.group,
                status='pending',
            )
            if record is None:
                continue

            try:
                result = service.send_text(phone, text)
            except Exception:  # noqa: BLE001
                logger.exception('session reminder failed (session=%s)', session.pk)
                result = {'success': False, 'error': 'exception'}

            if _finalize_message(record, result):
                sent += 1
            else:
                failed += 1

    return f'Session reminders: {sent} sent, {failed} failed'
