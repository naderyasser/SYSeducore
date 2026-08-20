import logging
from datetime import timedelta

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import ajax_supervisor_required
from apps.attendance.models import ActivityLog

from .models import Payment, PaymentAmountError

logger = logging.getLogger(__name__)

GENERIC_ERROR = 'تعذر إتمام العملية، حاول مرة أخرى'


def _error(message, status=400):
    """
    JSON error body. Both ``error`` and ``message`` are populated because the
    two payment endpoints historically used different keys and the templates
    read one or the other.
    """
    return JsonResponse(
        {'success': False, 'error': message, 'message': message},
        status=status,
    )


def _activate_student_for_payment(payment, user=None):
    """
    After a payment is marked as paid, let the student pass the attendance
    scanner immediately by:
      1. Activating the student's subscription (30-day expiry).
      2. Re-activating the *existing* StudentGroupEnrollment for this group.

    It deliberately does **not** create an enrollment: paying for a group the
    student was never enrolled in used to silently enroll them (and the
    scanner then treated it as a real registration). A missing enrollment is
    recorded in the activity log instead so the desk can fix it properly.

    Signature is public API — ``apps.attendance.views`` imports it.
    """
    from apps.students.models import StudentGroupEnrollment

    student = payment.student

    # 1. Activate subscription (30 days from today) — but only move the expiry
    # FORWARD. A student who already paid through a later date must not have
    # that date shortened by this shorter (30-day) grant.
    grace_date = timezone.localdate() + timedelta(days=30)
    if not student.subscription_expiry_date or student.subscription_expiry_date < grace_date:
        student.activate_subscription(days=30)
    else:
        student.last_payment_date = timezone.localdate()
        student.is_active = True
        student.save()

    # 2. Re-activate an existing enrollment for the payment's group.
    enrollment = StudentGroupEnrollment.objects.filter(
        student=student,
        group=payment.group,
    ).first()

    reactivated = False
    if enrollment is not None and not enrollment.is_active:
        enrollment.is_active = True
        enrollment.save(update_fields=['is_active'])
        reactivated = True

    # Log the activation
    if user:
        if enrollment is None:
            detail = ' — تنبيه: الطالب غير مسجل في هذه المجموعة (لم يتم إنشاء تسجيل)'
        elif reactivated:
            detail = ' — تم إعادة تفعيل التسجيل في المجموعة'
        else:
            detail = ''
        ActivityLog.log(
            user=user,
            action='payment_record',
            description=(
                f'تسديد + تفعيل: {student.full_name} — '
                f'{payment.group.group_name} — '
                f'الاشتراك حتى {student.subscription_expiry_date}{detail}'
            ),
            target_model='Payment',
            target_id=payment.pk,
        )

    return enrollment


@ajax_supervisor_required
@require_http_methods(["POST"])
def record_payment(request, payment_id):
    """
    API endpoint لتسجيل دفع

    Money-moving: supervisor or admin only. The whole operation (ledger row,
    payment reconciliation, subscription activation, enrollment
    re-activation, activity log) runs inside one transaction so a failure
    half-way cannot leave the student paid-but-inactive.
    """
    try:
        payment = Payment.objects.select_related('student', 'group').get(pk=payment_id)
    except Payment.DoesNotExist:
        return _error('سجل الدفع غير موجود', status=404)

    raw_amount = request.POST.get('amount', '0')

    try:
        with transaction.atomic():
            txn = payment.record_transaction(
                raw_amount,
                user=request.user,
                note='تحصيل من صفحة المدفوعات',
            )

            if txn is None:
                # Nothing moved (amount = 0): do not extend the subscription
                # or write a receipt for a no-op.
                pass
            elif payment.status == 'paid':
                _activate_student_for_payment(payment, user=request.user)
            else:
                ActivityLog.log(
                    user=request.user, action='payment_record',
                    description=(
                        f'تسجيل دفعة جزئية: {txn.amount} جنيه للطالب '
                        f'{payment.student.full_name} — {payment.group.group_name}'
                    ),
                    target_model='Payment', target_id=payment.pk, request=request,
                )
    except PaymentAmountError as exc:
        return _error(str(exc), status=400)
    except Exception:
        logger.exception('record_payment failed for payment %s', payment_id)
        return _error(GENERIC_ERROR, status=500)

    return JsonResponse({
        'success': True,
        'new_amount_paid': float(payment.amount_paid),
        'amount_paid': float(payment.amount_paid),
        'remaining': float(payment.remaining),
        'status': payment.status,
        'status_display': payment.get_status_display(),
    })


@ajax_supervisor_required
@require_http_methods(["POST"])
def mark_as_paid(request, payment_id):
    """
    تسديد الدفعة بالكامل + تفعيل الاشتراك والتسجيل

    Money-moving: supervisor or admin only, atomic, and every movement is
    written to the payment ledger with the user who took the money.
    """
    try:
        payment = Payment.objects.select_related('student', 'group').get(pk=payment_id)
    except Payment.DoesNotExist:
        return _error('الدفعة غير موجودة', status=404)

    try:
        with transaction.atomic():
            txn = payment.settle_full(user=request.user, note='تسديد كامل من صفحة المدفوعات')
            if txn is not None:
                # Only a real money movement re-activates the student — a
                # replay on an already-settled payment must not undo a
                # deliberate deactivation (settle_full returns None then).
                _activate_student_for_payment(payment, user=request.user)
    except PaymentAmountError as exc:
        return _error(str(exc), status=400)
    except Exception:
        logger.exception('mark_as_paid failed for payment %s', payment_id)
        return _error(GENERIC_ERROR, status=500)

    message = (
        'تم تسديد الدفعة وتفعيل الاشتراك بنجاح' if txn is not None
        else 'الدفعة مسددة بالفعل'
    )
    return JsonResponse({
        'success': True,
        'message': message,
        'payment': {
            'payment_id': payment.payment_id,
            'amount_paid': float(payment.amount_paid),
            'status': payment.status,
        }
    })
