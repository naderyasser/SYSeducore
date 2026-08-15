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
            status = attendance.status if attendance else 'absent'
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
