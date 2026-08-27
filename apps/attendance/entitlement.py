"""
Session-based entitlement — the single decision function for "can this
student attend this group right now, financially speaking".

Replaces the old global 30-day ``Student.is_subscription_active()`` check
and the calendar-month counting inside
``AttendanceService.check_financial_status``. Entitlement is now scoped to
one (student, group) pair via that group's current
:class:`~apps.teachers.models.GroupCycle` — paying for one teacher never
touches another.

Kept deliberately separate from ``services.py`` (1000+ lines already) so the
decision ladder can be unit-tested in isolation, with an injectable
``today`` and without a scanner request in the loop.
"""
from django.conf import settings
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.pricing import prorated_fee

#: Free sessions granted before payment is required, once a student has
#: already paid this group at least once. Overridable via
#: ``settings.BILLING_GRACE_SESSIONS``.
#:
#: Read live via ``getattr(settings, ...)`` at call time — NOT cached into a
#: module constant — so ``@override_settings`` in tests (and a runtime env
#: change) actually takes effect. A previous version cached this at import
#: time, which made ``override_settings(ENABLE_FIRST_MONTH_STRICT_PAYMENT=…)``
#: a silent no-op.
GRACE_SESSIONS_DEFAULT = 2


def _has_ever_paid(student, group):
    """
    Has this student ever settled a payment for this group?

    Replaces ``is_student_first_month_in_group`` (removed): that helper
    compared ``scan_time`` against the calendar month, which could disagree
    with ``check_financial_status``'s own ``session_date``-based counting
    across a month boundary. "Has a paid Payment row ever existed for this
    (student, group)" is unambiguous and cycle-agnostic.
    """
    return Payment.objects.filter(student=student, group=group, status='paid').exists()


def first_consumed_session(student, cycle):
    """
    The session at which this student's counting starts — their first *real*
    attendance in ``cycle`` (present / late / exception, never a bare absence).

    The client's rule is explicit: counting begins at the first session the
    student actually attends, and only from then on does an absence burn a
    session ("بمجرد تسجيل أول حضور للطالب، يبدأ السيستم في عد الحصص سواء
    حضر أو غاب"). ``auto_mark_absent_sessions`` writes an absence row for
    every *enrolled* student whether or not they have ever shown up, so
    counting from the start of the cycle would charge a late-joining student
    for sessions they were never at — and, since their entitlement is
    pro-rated to what is left, would exhaust it before their first lesson.

    Returns the :class:`~apps.attendance.models.Session`, or ``None`` when
    the student has no qualifying attendance yet.
    """
    from .models import Attendance

    first = (
        Attendance.objects.filter(
            student=student, session__cycle=cycle, session__is_cancelled=False,
        )
        .exclude(status='absent')
        .order_by('session__session_date')
        .select_related('session')
        .first()
    )
    return first.session if first else None


def _consumed_sessions(student, cycle, anchor_session=None):
    """
    Count of non-cancelled sessions in ``cycle`` this student has consumed
    (present, late, absent or exception all count — an absence burns a
    session, once counting has started).

    Anchored on the start session's **date**, never on its
    ``sequence_in_cycle``. Sequence numbers are renumbered whenever a session
    is cancelled or one is backfilled at an earlier date, so a stored
    sequence silently comes to point at a different lesson; the date does
    not move. (``Payment.entitlement_start_seq`` stays a frozen snapshot for
    pricing — that one is *meant* not to follow later changes.)
    """
    from .models import Attendance

    if anchor_session is None:
        anchor_session = first_consumed_session(student, cycle)
        if anchor_session is None:
            return 0

    return Attendance.objects.filter(
        student=student,
        session__cycle=cycle,
        session__is_cancelled=False,
        session__session_date__gte=anchor_session.session_date,
    ).count()


def evaluate(enrollment, cycle, *, payment=None, today=None):
    """
    Decide whether ``enrollment.student`` may attend ``enrollment.group``
    right now, given the group's current ``cycle`` (a
    :class:`~apps.teachers.models.GroupCycle`, or ``None`` for a group that
    is not cycle-billed at all).

    Read-only: never creates or mutates a ``Payment`` row (a caller that
    needs a row, e.g. to collect money, creates it explicitly).

    Returns a dict compatible with the historical
    ``check_financial_status`` shape:
      * allow:  ``{'allowed': True, ...}`` plus optional ``exempt``,
                ``exception_applied``/``exception_id``/``exception_reason``,
                ``grace_period``/``grace_until``, ``grace_sessions``/
                ``grace_sessions_left``, ``sessions_consumed``/
                ``sessions_total``, ``cycle_id``/``cycle_index``.
      * reject: ``{'allowed': False, 'reason': <Arabic>, 'error_type': ...}``,
                and for ``payment_required`` also ``payment_id``,
                ``student_id``, ``group_id``, ``amount_due``.
    """
    today = today or timezone.localdate()

    if enrollment is None or not enrollment.is_active:
        return {'allowed': False, 'reason': 'ممنوع الدخول: غير مسجل في هذه المجموعة',
                'error_type': 'not_enrolled'}

    student, group = enrollment.student, enrollment.group

    if enrollment.financial_status == 'exempt':
        return {'allowed': True, 'exempt': True}

    if cycle is None:
        # sessions_per_month == 0 on this group: not billed by cycle at all.
        return {'allowed': True, 'unlimited': True}

    if payment is None:
        payment = Payment.objects.filter(student=student, cycle=cycle).first()

    if payment is not None and payment.status == 'paid':
        consumed = payment.sessions_attended
        total = payment.sessions_total
        if consumed < total:
            return {
                'allowed': True,
                'sessions_consumed': consumed, 'sessions_total': total,
                'cycle_id': cycle.cycle_id, 'cycle_index': cycle.index,
            }
        return {
            'allowed': False,
            'reason': f'تم استنفاد جميع الحصص ({total} حصة) لهذه الدورة. يرجى تجديد الاشتراك.',
            'error_type': 'sessions_exhausted',
            'sessions_attended': consumed, 'sessions_limit': total,
        }

    # Not paid (or no Payment row yet) — grace, exception, manual grace_until,
    # then reject.
    ever_paid = _has_ever_paid(student, group)
    strict_first_cycle = getattr(settings, 'ENABLE_FIRST_MONTH_STRICT_PAYMENT', True)
    grace_sessions = getattr(settings, 'BILLING_GRACE_SESSIONS', GRACE_SESSIONS_DEFAULT)
    allowance = 0 if (strict_first_cycle and not ever_paid) else grace_sessions

    anchor = payment.entitlement_start_session if payment is not None else None
    grace_used = _consumed_sessions(student, cycle, anchor_session=anchor)

    if grace_used < allowance:
        return {
            'allowed': True, 'grace_sessions': True,
            'grace_sessions_left': allowance - grace_used,
            'cycle_id': cycle.cycle_id, 'cycle_index': cycle.index,
        }

    from .services import AttendanceService  # local import: avoids a cycle
    exception = AttendanceService.check_exception_status(student, group, exception_type='payment')
    if exception:
        return {
            'allowed': True, 'exception_applied': True,
            'exception_id': exception.exception_id,
            'exception_reason': exception.reason_display,
        }

    if enrollment.grace_until and enrollment.grace_until >= today:
        return {
            'allowed': True, 'grace_period': True,
            'grace_until': enrollment.grace_until.isoformat(),
        }

    reason = 'ممنوع الدخول: الدفع مطلوب'
    if not ever_paid:
        reason += ' (أول اشتراك)'
    amount_due = prorated_fee(
        enrollment,
        cycle_size=cycle.sessions_planned,
        first_sequence=(grace_used + 1),
        group=group,
    )
    return {
        'allowed': False,
        'reason': reason,
        'error_type': 'payment_required',
        'payment_id': payment.payment_id if payment is not None else None,
        'student_id': student.student_id,
        'group_id': group.group_id,
        'amount_due': float(amount_due),
    }
