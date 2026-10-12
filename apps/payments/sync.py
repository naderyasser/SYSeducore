"""
ربط التعديلات ببعض — طلب العميل «اربط كله بكله» (2026-10-12).

Every number on an invoice or a settlement line is computed once — from the
group, the student's enrollment terms and the attendance rows — and then
stored. Before this module an edit upstream never reached those stored
copies: a new group price left the current cycle's invoices at the old one
(while the gate already asked for the new one), a new cycle size left the
open cycle and every entitlement on it at the old count, and a draft
settlement kept the numbers it was built with until someone pressed
«تحديث».

The rule for money is the same everywhere here: an invoice is re-priced only
while it is still exactly what the system generated — no money on it, no
ledger rows, no package, and an amount equal to what the *old* terms would
have produced. A discount or exemption typed at the desk, or anything
already collected, is never rewritten. Entitlement (``sessions_total``)
follows the cycle size on every invoice, paid ones included, because the
gate compares it with the sessions consumed in that very cycle.
"""
import logging

from django.db import transaction

from .models import Payment, TeacherSettlement, to_money
from .pricing import base_fee_parts, entitled_sessions, prorate

logger = logging.getLogger(__name__)

#: A save that writes any of these can change what a settlement line shows.
MONEY_FIELDS = frozenset({
    'amount_due', 'amount_paid', 'status', 'is_exempt', 'cycle', 'group', 'student',
})


# ---------------------------------------------------------------------------
#  Invoices
# ---------------------------------------------------------------------------

def _join_sequence(payment, cycle_size):
    """
    The lesson (1-based) this invoice was priced from, read back from its
    entitlement. Every creation path writes
    ``sessions_total = entitled_sessions(cycle_size, seq)`` — that is,
    ``cycle_size - seq + 1`` — so the join point survives in the row even
    for a student who has not attended yet (whose
    ``billing_start_sequence`` has moved on since the invoice was cut).
    ``None`` for a row that does not fit the cycle (legacy data).
    """
    total = payment.sessions_total or 0
    if cycle_size <= 0 or total <= 0 or total > cycle_size:
        return None
    return cycle_size - total + 1


def _untouched(payment):
    """No money has moved on this invoice and no package priced it."""
    return (
        payment.package_id is None
        and to_money(payment.amount_paid or 0) == 0
        and not payment.transactions.exists()
    )


def _resync_invoice(payment, *, old_base, new_base, old_size, new_size):
    """
    Bring one invoice on an unclosed cycle in line with new terms.
    ``old_base``/``new_base`` are full-cycle fees (``None`` — no enrollment
    to price from — leaves the amount alone). Returns ``True`` if the amount
    changed.
    """
    seq = _join_sequence(payment, old_size)
    if seq is None:
        return False
    new_seq = min(seq, new_size)
    fields = []

    new_total = entitled_sessions(cycle_size=new_size, first_sequence=new_seq)
    if payment.sessions_total != new_total:
        payment.sessions_total = new_total
        fields.append('sessions_total')

    repriced = False
    if (old_base is not None and _untouched(payment)
            and to_money(payment.amount_due) == prorate(old_base, cycle_size=old_size, first_sequence=seq)):
        new_due = prorate(new_base, cycle_size=new_size, first_sequence=new_seq)
        if new_due != to_money(payment.amount_due):
            payment.amount_due = new_due
            payment.is_exempt = new_due <= 0
            payment.status = payment._derive_status(to_money(0))
            fields += ['amount_due', 'is_exempt', 'status']
            repriced = True

    if fields:
        payment.save(update_fields=fields + ['updated_at'])
    return repriced


def held_in_open_cycle(group):
    """Non-cancelled lessons already held in ``group``'s running cycle."""
    from apps.attendance.models import Session

    return Session.objects.filter(
        cycle__group=group, cycle__started_on__isnull=False,
        cycle__closed_on__isnull=True, is_cancelled=False,
    ).count()


def resync_group(group, *, old_fee, old_sessions_per_month):
    """
    Push a saved group's price and cycle size onto everything still open:
    the ``sessions_planned`` of its unclosed cycles (the running one and any
    reserved for a package) and every invoice on them. Closed cycles are
    settled history and stay as they were. Returns
    ``{'cycles': n, 'invoices': n}`` — how many of each changed.
    """
    from apps.students.models import StudentGroupEnrollment
    from apps.teachers.models import GroupCycle

    new_size = group.sessions_per_month or 0
    size_changed = bool(old_sessions_per_month) and bool(new_size) and new_size != old_sessions_per_month
    fee_changed = to_money(old_fee or 0) != to_money(group.standard_fee or 0)
    result = {'cycles': 0, 'invoices': 0}
    if not (size_changed or fee_changed):
        return result

    enrollments = {
        e.student_id: e for e in StudentGroupEnrollment.objects.filter(group=group)
    }
    with transaction.atomic():
        cycles = GroupCycle.objects.select_for_update().filter(group=group, closed_on__isnull=True)
        for cycle in cycles:
            old_size = cycle.sessions_planned
            cycle_size = new_size if size_changed else old_size
            if cycle_size != old_size:
                cycle.sessions_planned = cycle_size
                cycle.save(update_fields=['sessions_planned'])
                result['cycles'] += 1
            for payment in Payment.objects.filter(cycle=cycle):
                enr = enrollments.get(payment.student_id)
                old_base = new_base = None
                if enr is not None:
                    old_base = base_fee_parts(enr.financial_status, enr.custom_fee, old_fee)
                    new_base = base_fee_parts(enr.financial_status, enr.custom_fee, group.standard_fee)
                if _resync_invoice(payment, old_base=old_base, new_base=new_base,
                                   old_size=old_size, new_size=cycle_size):
                    result['invoices'] += 1
    return result


def resync_enrollment(enrollment, *, old_status, old_custom_fee):
    """
    A student's financial terms in a group changed (normal ↔ exempt ↔
    symbolic, or a new custom price): re-price their untouched invoices on
    the group's unclosed cycles. Returns how many changed.
    """
    group = enrollment.group
    old_base = base_fee_parts(old_status, old_custom_fee, group.standard_fee)
    new_base = base_fee_parts(enrollment.financial_status, enrollment.custom_fee, group.standard_fee)
    if old_base == new_base:
        return 0
    changed = 0
    payments = (
        Payment.objects.filter(
            student_id=enrollment.student_id, group=group,
            cycle__isnull=False, cycle__closed_on__isnull=True,
        ).select_related('cycle')
    )
    for payment in payments:
        size = payment.cycle.sessions_planned
        if _resync_invoice(payment, old_base=old_base, new_base=new_base,
                           old_size=size, new_size=size):
            changed += 1
    # The line's «السعر الكامل» and financial status come from the
    # enrollment, so the sheet moves even when no invoice did.
    teacher_id = group.teacher_id
    transaction.on_commit(lambda: refresh_draft_settlements([teacher_id]))
    return changed


def drop_unused_invoices(student, group):
    """
    A student taken off a group no longer owes the running cycle they never
    used: delete their invoices on its unclosed cycles that carry no money,
    no package, no consumed session and no settlement line. Anything they
    did use stays — that is a real debt. Returns how many were removed.
    """
    removed = 0
    candidates = Payment.objects.filter(
        student=student, group=group, cycle__isnull=False, cycle__closed_on__isnull=True,
        sessions_attended=0,
    )
    for payment in candidates:
        if _untouched(payment) and not payment.settlement_lines.exists():
            payment.delete()
            removed += 1
    return removed


# ---------------------------------------------------------------------------
#  Draft settlements
# ---------------------------------------------------------------------------

def refresh_settlement_if_draft(settlement):
    """Recompute a draft sheet in place (approved ones are frozen)."""
    from .models import SettlementLockedError
    from .services import SettlementService

    if settlement.status != TeacherSettlement.STATUS_DRAFT:
        return settlement
    try:
        return SettlementService.build_or_refresh(
            settlement.teacher, settlement.period_start, settlement.period_end,
        )
    except SettlementLockedError:   # approved between the read and now
        settlement.refresh_from_db()
        return settlement


def refresh_draft_settlements(teacher_ids, *, on_date=None, month=None):
    """
    Recompute every draft sheet of ``teacher_ids`` — only those whose period
    holds ``on_date`` (a cycle's start) or overlaps ``month`` (a legacy
    month-billed invoice) when either is given. Never raises: a sheet that
    fails to rebuild is logged and keeps its last numbers rather than
    failing the edit that triggered it.
    """
    teacher_ids = [t for t in set(teacher_ids) if t]
    if not teacher_ids:
        return
    drafts = TeacherSettlement.objects.filter(
        teacher_id__in=teacher_ids, status=TeacherSettlement.STATUS_DRAFT,
    ).select_related('teacher')
    if on_date is not None:
        drafts = drafts.filter(period_start__lte=on_date, period_end__gte=on_date)
    elif month is not None:
        drafts = drafts.filter(period_end__gte=month.replace(day=1))
    for settlement in drafts:
        if month is not None and on_date is None and settlement.period_start.replace(day=1) > month:
            continue
        try:
            # Own savepoint: a failed rebuild must not poison a surrounding
            # transaction (the edit that triggered it still commits).
            with transaction.atomic():
                refresh_settlement_if_draft(settlement)
        except Exception:  # noqa: BLE001 — see docstring
            logger.exception('draft settlement %s refresh failed', settlement.pk)


def payment_changed(payment):
    """
    After a payment's money moved (or it was created/deleted), refresh the
    draft sheet of its group's teacher that covers its cycle. Deferred to
    commit so a multi-row edit refreshes once the rows are final.
    """
    from apps.teachers.models import Group, GroupCycle

    # Read through the ids, not the relations: on a purge the group or cycle
    # row may already be gone by the time the payment's delete signal fires.
    teacher_id = (
        Group.all_objects.filter(pk=payment.group_id).values_list('teacher_id', flat=True).first()
        if payment.group_id else None
    )
    if not teacher_id:
        return
    if payment.cycle_id:
        started = (
            GroupCycle.objects.filter(pk=payment.cycle_id).values_list('started_on', flat=True).first()
        )
        if started is None:
            return   # a reserved cycle belongs to no period yet
        transaction.on_commit(lambda: refresh_draft_settlements([teacher_id], on_date=started))
    elif payment.month:
        month = payment.month
        transaction.on_commit(lambda: refresh_draft_settlements([teacher_id], month=month))
