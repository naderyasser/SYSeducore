"""
Payment → entitlement activation — scoped to exactly one (student, group).

Replaces the old ``_activate_student_for_payment`` (apps/payments/api_views.py),
which extended a *global* ``Student.subscription_expiry_date`` and could also
flip ``Student.is_active`` — so paying for one teacher silently re-activated
a student the desk had deliberately deactivated, and touched every other
group they were enrolled in. This version never reads or writes anything on
``Student`` itself.
"""
import logging

from django.utils import timezone

from apps.attendance.models import ActivityLog

logger = logging.getLogger(__name__)


def activate_payment(payment, *, paid_on=None, user=None, request=None):
    """
    Called right after a payment is settled (fully or partially into
    ``status='paid'``). Does exactly two things, both scoped to
    ``payment.group``:

    1. Re-activates the *existing* :class:`~apps.students.models.
       StudentGroupEnrollment` for this student+group, if it was inactive.
       Never creates one — paying for a group the student was never
       enrolled in is recorded in the activity log instead, so the desk
       fixes the enrollment deliberately rather than it happening as a
       side-effect of a payment.
    2. Stamps the entitlement anchor (``entitlement_start_session`` /
       ``entitlement_start_seq``) on ``payment`` if it doesn't have one yet
       and the student already has a qualifying attendance in the cycle —
       the first non-cancelled attendance on/after ``paid_on``. If none
       exists yet, leaves both null; the next scan
       (``AttendanceService.update_payment_sessions``) sets it.

    Returns the enrollment (``None`` if none exists to reactivate).
    """
    from apps.students.models import StudentGroupEnrollment

    paid_on = paid_on or payment.paid_on or timezone.localdate()
    if payment.paid_on != paid_on:
        payment.paid_on = paid_on
        payment.save(update_fields=['paid_on'])

    student = payment.student

    enrollment = StudentGroupEnrollment.objects.filter(
        student=student, group=payment.group,
    ).first()

    reactivated = False
    if enrollment is not None and not enrollment.is_active:
        enrollment.is_active = True
        enrollment.save(update_fields=['is_active'])
        reactivated = True

    if payment.cycle_id and payment.entitlement_start_session_id is None:
        from apps.attendance.models import Attendance
        first = (
            Attendance.objects.filter(
                student=student, session__cycle_id=payment.cycle_id,
                session__is_cancelled=False, session__session_date__gte=paid_on,
            )
            .exclude(status='absent')
            # By date, not by sequence_in_cycle — sequences are renumbered
            # when a session is cancelled or backfilled, dates are not.
            .order_by('session__session_date')
            .select_related('session')
            .first()
        )
        if first is not None:
            payment.entitlement_start_session = first.session
            payment.entitlement_start_seq = first.session.sequence_in_cycle
            payment.save(update_fields=['entitlement_start_session', 'entitlement_start_seq'])

    if user:
        if enrollment is None:
            detail = ' — تنبيه: الطالب غير مسجل في هذه المجموعة (لم يتم إنشاء تسجيل)'
        elif reactivated:
            detail = ' — تم إعادة تفعيل التسجيل في المجموعة'
        else:
            detail = ''
        cycle_label = f'الدورة {payment.cycle.index}' if payment.cycle_id else 'بدون دورة'
        ActivityLog.log(
            user=user,
            action='payment_record',
            description=(
                f'تسديد: {student.full_name} — {payment.group.group_name} — '
                f'{cycle_label} — تاريخ الدفع {paid_on}{detail}'
            ),
            target_model='Payment',
            target_id=payment.pk,
            request=request,
        )

    return enrollment
