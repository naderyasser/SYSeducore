import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import ajax_supervisor_required, ajax_admin_required
from apps.attendance.models import ActivityLog

from .activation import activate_payment
from .models import Payment, PaymentAmountError, SettlementLockedError

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


#: Kept as an alias for one release — ``apps.attendance.views`` and
#: ``apps.payments.tests`` still import this name directly. The real
#: implementation moved to ``apps.payments.activation.activate_payment`` and
#: is per-(student, group) only: it no longer touches ``Student`` at all.
_activate_student_for_payment = activate_payment


def _parse_paid_on(request):
    """
    Optional explicit "تاريخ الدفع" from the desk. Returns ``None`` (→ today)
    on absence or an unparseable value rather than rejecting the whole
    request over a cosmetic date field.
    """
    from datetime import date
    raw = request.POST.get('paid_on')
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


@ajax_supervisor_required
@require_http_methods(["POST"])
def record_payment(request, payment_id):
    """
    API endpoint لتسجيل دفع

    Money-moving: supervisor or admin only. The whole operation (ledger row,
    payment reconciliation, entitlement activation, enrollment
    re-activation, activity log) runs inside one transaction so a failure
    half-way cannot leave the student paid-but-inactive.
    """
    try:
        payment = Payment.objects.select_related('student', 'group').get(pk=payment_id)
    except Payment.DoesNotExist:
        return _error('سجل الدفع غير موجود', status=404)

    raw_amount = request.POST.get('amount', '0')
    paid_on = _parse_paid_on(request)

    try:
        with transaction.atomic():
            txn = payment.record_transaction(
                raw_amount,
                user=request.user,
                note='تحصيل من صفحة المدفوعات',
                effective_on=paid_on,
            )

            if txn is None:
                # Nothing moved (amount = 0): do not activate entitlement
                # or write a receipt for a no-op.
                pass
            elif payment.status == 'paid':
                activate_payment(payment, paid_on=paid_on, user=request.user, request=request)
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

    paid_on = _parse_paid_on(request)

    try:
        with transaction.atomic():
            txn = payment.settle_full(
                user=request.user, note='تسديد كامل من صفحة المدفوعات', effective_on=paid_on,
            )
            if txn is not None:
                # Only a real money movement re-activates the student — a
                # replay on an already-settled payment must not undo a
                # deliberate deactivation (settle_full returns None then).
                activate_payment(payment, paid_on=paid_on, user=request.user, request=request)
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


def _get_or_create_open_cycle_payment(student, group):
    """
    The Payment row this student owes for ``group``'s currently open cycle,
    creating one (priced via ``prorated_fee`` for a first-ever, mid-cycle
    join) if it doesn't exist yet. ``None`` if the group isn't cycle-billed
    at all (``sessions_per_month == 0``).
    """
    from django.utils import timezone
    from apps.attendance.entitlement import billing_start_sequence
    from apps.teachers.cycles import open_cycle_for
    from apps.payments.pricing import entitled_sessions, prorated_fee
    from apps.students.models import StudentGroupEnrollment

    if not group.sessions_per_month:
        return None
    cycle = open_cycle_for(group)
    payment = Payment.objects.filter(student=student, cycle=cycle).first()
    if payment is not None:
        return payment

    enrollment = StudentGroupEnrollment.objects.filter(student=student, group=group).first()
    # This is the desk's collection dialog, so it is the path a mid-cycle
    # joiner actually walks up and pays through — it must pro-rate. It used to
    # pass ``first_sequence=1`` (full cycle fee for everyone), which is exactly
    # the "charge a full month, refund the difference on paper" the session
    # billing was meant to end.
    start_seq = billing_start_sequence(student, cycle)
    fee = prorated_fee(
        enrollment, cycle_size=cycle.sessions_planned,
        first_sequence=start_seq, group=group,
    ) if enrollment else 0
    return Payment.objects.create(
        student=student, group=group, cycle=cycle,
        month=(cycle.started_on or timezone.localdate()).replace(day=1),
        amount_due=fee, status='unpaid',
        # The row must promise only what was paid for, or entitlement would
        # hand a half-cycle payer a full cycle of lessons.
        sessions_total=entitled_sessions(
            cycle_size=cycle.sessions_planned, first_sequence=start_seq,
        ),
    )


@ajax_supervisor_required
@require_http_methods(["POST"])
def collect_payment(request):
    """
    "تسجيل دفع" — the quick per-(student, group) collection dialog that
    replaces the old "تفعيل الاشتراك" button. Body:
      * student_id, group_id (required)
      * amount (required) — the amount actually handed over
      * paid_on (optional, YYYY-MM-DD, defaults to today)
      * package_cycles (optional, int >= 2) — pay for several upcoming
        cycles at once (see ``apps.payments.models.PaymentPackage``); when
        given, ``amount`` is the TOTAL handed over across all of them.
    """
    from django.utils import timezone
    from apps.students.models import Student, StudentGroupEnrollment
    from apps.teachers.models import Group
    from apps.teachers.cycles import ensure_next
    from apps.payments.pricing import base_fee
    from apps.payments.models import PaymentPackage, to_money

    try:
        student_id = request.POST.get('student_id')
        group_id = request.POST.get('group_id')
        if not student_id or not group_id:
            return _error('student_id و group_id مطلوبان')

        student = Student.all_objects.get(pk=student_id)
        group = Group.objects.get(pk=group_id)

        if not StudentGroupEnrollment.objects.filter(student=student, group=group).exists():
            return _error('الطالب غير مسجل في هذه المجموعة', status=404)

        raw_amount = request.POST.get('amount', '0')
        paid_on = _parse_paid_on(request)

        try:
            package_cycles = int(request.POST.get('package_cycles') or 0)
        except (TypeError, ValueError):
            return _error('عدد الدورات غير صالح')
        if package_cycles < 0 or package_cycles > 24:
            return _error('عدد الدورات يجب أن يكون بين 0 و 24')

        with transaction.atomic():
            if package_cycles >= 2:
                if not group.sessions_per_month:
                    return _error('هذه المجموعة غير محسوبة بالحصص')
                enrollment = StudentGroupEnrollment.objects.get(student=student, group=group)
                first_payment = _get_or_create_open_cycle_payment(student, group)
                extra_cycles = ensure_next(group, package_cycles - 1)

                list_amount = to_money(first_payment.amount_due) + to_money(
                    base_fee(enrollment, group)
                ) * (package_cycles - 1)
                total_amount = to_money(raw_amount)
                per_extra = to_money(total_amount / package_cycles)
                first_amount = total_amount - per_extra * (package_cycles - 1)

                package = PaymentPackage.objects.create(
                    student=student, group=group, cycles=package_cycles,
                    total_amount=total_amount, list_amount=list_amount,
                    paid_on=paid_on or timezone.localdate(),
                    created_by=request.user,
                )

                first_payment.amount_due = first_amount
                first_payment.package = package
                first_payment.save(update_fields=['amount_due', 'package'])
                first_payment.settle_full(user=request.user, note='دفعة باقة', effective_on=paid_on)
                activate_payment(first_payment, paid_on=paid_on, user=request.user, request=request)

                for extra_cycle in extra_cycles:
                    p = Payment.objects.create(
                        student=student, group=group, cycle=extra_cycle,
                        month=timezone.localdate().replace(day=1),
                        amount_due=per_extra, status='unpaid',
                        sessions_total=extra_cycle.sessions_planned,
                        package=package,
                    )
                    p.settle_full(user=request.user, note='دفعة باقة', effective_on=paid_on)

                ActivityLog.log(
                    user=request.user, action='payment_record',
                    description=(
                        f'باقة {package_cycles} دورات: {student.full_name} — '
                        f'{group.group_name} — {total_amount} ج.م'
                    ),
                    target_model='Payment', target_id=first_payment.pk, request=request,
                )
                payment = first_payment
            else:
                payment = _get_or_create_open_cycle_payment(student, group)
                if payment is None:
                    return _error('هذه المجموعة غير محسوبة بالحصص')
                payment.record_transaction(
                    raw_amount, user=request.user, note='تسجيل دفع', effective_on=paid_on,
                )
                if payment.status == 'paid':
                    activate_payment(payment, paid_on=paid_on, user=request.user, request=request)
    except (Student.DoesNotExist, Group.DoesNotExist):
        return _error('الطالب أو المجموعة غير موجودة', status=404)
    except PaymentAmountError as exc:
        return _error(str(exc), status=400)
    except Exception:
        logger.exception('collect_payment failed')
        return _error(GENERIC_ERROR, status=500)

    return JsonResponse({
        'success': True,
        'message': 'تم تسجيل الدفع بنجاح',
        'payment': {
            'payment_id': payment.payment_id,
            'amount_paid': float(payment.amount_paid),
            'amount_due': float(payment.amount_due),
            'status': payment.status,
        },
    })


# ─────────────────────────────────────────────────────────────
# Teacher settlement — build/refresh, per-line edit, approve/reopen
# ─────────────────────────────────────────────────────────────

def _settlement_totals_payload(settlement):
    return {
        'settlement_id': settlement.settlement_id,
        'status': settlement.status,
        'computed_gross': float(settlement.computed_gross),
        'adjusted_gross': float(settlement.adjusted_gross),
        'center_share': float(settlement.center_share),
        'teacher_share': float(settlement.teacher_share),
        'updated_at': settlement.updated_at.isoformat(),
    }


def _line_payload(line):
    return {
        'line_id': line.line_id,
        'effective_amount': float(line.effective_amount),
        'line_center_share': float(line.line_center_share),
        'line_teacher_share': float(line.line_teacher_share),
        'is_excluded': line.is_excluded,
        'is_free': line.is_free,
    }


@ajax_admin_required
@require_http_methods(["POST"])
def settlement_build(request):
    """
    ابنِ (أو أعِد حساب) كشف تصفية لمدرس عن فترة معينة.
    Body: teacher_id, period_start (YYYY-MM-DD), period_end (YYYY-MM-DD).
    """
    from datetime import date as _date
    from apps.teachers.models import Teacher
    from .services import SettlementService

    teacher_id = request.POST.get('teacher_id')
    raw_start = request.POST.get('period_start')
    raw_end = request.POST.get('period_end')
    if not (teacher_id and raw_start and raw_end):
        return _error('teacher_id و period_start و period_end مطلوبة')

    try:
        teacher = Teacher.all_objects.get(pk=teacher_id)
        period_start = _date.fromisoformat(raw_start)
        period_end = _date.fromisoformat(raw_end)
    except Teacher.DoesNotExist:
        return _error('المدرس غير موجود', status=404)
    except ValueError:
        return _error('تاريخ غير صالح')

    if period_end < period_start:
        return _error('تاريخ النهاية قبل تاريخ البداية')

    try:
        settlement = SettlementService.build_or_refresh(teacher, period_start, period_end, user=request.user)
    except SettlementLockedError as exc:
        return _error(str(exc), status=409)

    ActivityLog.log(
        user=request.user, action='settlement_create',
        description=f'بناء/تحديث كشف تصفية: {teacher.full_name} — {period_start} إلى {period_end}',
        target_model='TeacherSettlement', target_id=settlement.pk, request=request,
    )
    return JsonResponse({'success': True, 'settlement': _settlement_totals_payload(settlement)})


@ajax_admin_required
@require_http_methods(["POST"])
def settlement_refresh(request, settlement_id):
    """أعِد حساب كشف مسودة قائم (لا يمس أي تعديل يدوي)."""
    from .models import TeacherSettlement
    from .services import SettlementService

    try:
        settlement = TeacherSettlement.objects.select_related('teacher').get(pk=settlement_id)
    except TeacherSettlement.DoesNotExist:
        return _error('الكشف غير موجود', status=404)

    try:
        settlement = SettlementService.build_or_refresh(
            settlement.teacher, settlement.period_start, settlement.period_end, user=request.user,
        )
    except SettlementLockedError as exc:
        return _error(str(exc), status=409)

    return JsonResponse({'success': True, 'settlement': _settlement_totals_payload(settlement)})


@ajax_admin_required
@require_http_methods(["POST"])
def settlement_line_update(request, line_id):
    """
    تعديل يدوي على سطر واحد: استبعاد، حالة مجانية، مبلغ مُعدَّل، نسبة
    مُعدَّلة، سبب. أي حقل غير مُرسَل يبقى بلا تغيير.
    """
    from .models import TeacherSettlementLine

    try:
        line = TeacherSettlementLine.objects.select_related('settlement', 'group', 'student').get(pk=line_id)
    except TeacherSettlementLine.DoesNotExist:
        return _error('السطر غير موجود', status=404)

    if line.settlement.is_approved:
        return _error('الكشف معتمد — يجب إعادة فتحه أولاً', status=409)

    if 'is_excluded' in request.POST:
        line.is_excluded = request.POST.get('is_excluded') in ('1', 'true', 'True', 'on')
    if 'is_free' in request.POST:
        line.is_free = request.POST.get('is_free') in ('1', 'true', 'True', 'on')
    if 'amount_override' in request.POST:
        raw = request.POST.get('amount_override')
        try:
            line.amount_override = Decimal(raw) if raw not in (None, '') else None
        except InvalidOperation:
            return _error('مبلغ غير صالح')
    if 'percentage_override' in request.POST:
        raw = request.POST.get('percentage_override')
        try:
            line.percentage_override = Decimal(raw) if raw not in (None, '') else None
        except InvalidOperation:
            return _error('نسبة غير صالحة')
    if 'override_reason' in request.POST:
        line.override_reason = request.POST.get('override_reason', '')[:255]

    line.apply()
    line.edited_by = request.user
    from django.utils import timezone as _tz
    line.edited_at = _tz.now()
    line.save()

    line.settlement.recalculate_totals()
    line.settlement.refresh_from_db()

    ActivityLog.log(
        user=request.user, action='settlement_update',
        description=f'تعديل سطر تصفية: {line.student.full_name} — {line.group.group_name}',
        target_model='TeacherSettlementLine', target_id=line.pk, request=request,
    )
    return JsonResponse({
        'success': True,
        'line': _line_payload(line),
        'totals': _settlement_totals_payload(line.settlement),
    })


@ajax_admin_required
@require_http_methods(["POST"])
def settlement_approve(request, settlement_id):
    from django.utils import timezone as _tz
    from .models import TeacherSettlement

    try:
        settlement = TeacherSettlement.objects.select_related('teacher').get(pk=settlement_id)
    except TeacherSettlement.DoesNotExist:
        return _error('الكشف غير موجود', status=404)

    if settlement.is_approved:
        return _error('الكشف معتمد بالفعل', status=409)

    settlement.status = TeacherSettlement.STATUS_APPROVED
    settlement.approved_by = request.user
    settlement.approved_at = _tz.now()
    settlement.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

    ActivityLog.log(
        user=request.user, action='settlement_approve',
        description=f'اعتماد كشف تصفية: {settlement.teacher.full_name} — {settlement.period_start} إلى {settlement.period_end} — {settlement.teacher_share} ج.م',
        target_model='TeacherSettlement', target_id=settlement.pk, request=request,
    )
    return JsonResponse({'success': True, 'settlement': _settlement_totals_payload(settlement)})


@ajax_admin_required
@require_http_methods(["POST"])
def settlement_reopen(request, settlement_id):
    """
    إعادة فتح كشف معتمد إلى مسودة — بلا إعادة حساب تلقائي، حتى لا تتحرك
    الأرقام تحت يد المستخدم دون علمه؛ يضغط "إعادة الحساب" بنفسه إن أراد.
    """
    from django.utils import timezone as _tz
    from .models import TeacherSettlement

    try:
        settlement = TeacherSettlement.objects.select_related('teacher').get(pk=settlement_id)
    except TeacherSettlement.DoesNotExist:
        return _error('الكشف غير موجود', status=404)

    if not settlement.is_approved:
        return _error('الكشف مسودة بالفعل', status=409)

    settlement.status = TeacherSettlement.STATUS_DRAFT
    settlement.reopened_by = request.user
    settlement.reopened_at = _tz.now()
    settlement.save(update_fields=['status', 'reopened_by', 'reopened_at', 'updated_at'])

    ActivityLog.log(
        user=request.user, action='settlement_reopen',
        description=f'إعادة فتح كشف تصفية: {settlement.teacher.full_name} — {settlement.period_start} إلى {settlement.period_end}',
        target_model='TeacherSettlement', target_id=settlement.pk, request=request,
    )
    return JsonResponse({'success': True, 'settlement': _settlement_totals_payload(settlement)})
