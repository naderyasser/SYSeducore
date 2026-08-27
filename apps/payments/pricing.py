"""
The single source of truth for a student's fee — replaces the four copies
that used to exist independently in ``students/models.py``,
``payments/services.py``, ``payments/views.py`` and ``attendance/tasks.py``.

Session-based billing needs one more thing those copies never had:
pro-ration for a student who joins a group's cycle after it has already
started (requirement: pay only for the sessions remaining in that cycle).
"""
from decimal import Decimal

from .models import to_money

ZERO = Decimal('0.00')


def base_fee_parts(financial_status, custom_fee, standard_fee):
    """
    The one pricing rule, given raw values (no query). ``exempt`` is free,
    ``symbolic`` uses the student's custom price for a *full* cycle, anything
    else pays the group's standard fee.
    """
    if financial_status == 'exempt':
        return ZERO
    if financial_status == 'symbolic':
        return to_money(custom_fee or 0)
    return to_money(standard_fee or 0)


def base_fee(enrollment, group=None):
    """
    Full-cycle fee for a :class:`~apps.students.models.StudentGroupEnrollment`.
    ``group`` may be passed to avoid the FK lookup when the caller already
    has it (enrollment.group would otherwise issue a query per call).
    """
    if enrollment is None:
        return ZERO
    return base_fee_parts(
        enrollment.financial_status,
        enrollment.custom_fee,
        (group or enrollment.group).standard_fee,
    )


def entitled_sessions(*, cycle_size, first_sequence):
    """
    How many of a cycle's sessions this student is entitled to, given they
    first attended (or were assigned) at ``first_sequence`` (1-based).

    A student present from session 1 of a 4-session cycle is entitled to all
    4; one who first appears at session 2 is entitled to 3.
    """
    if cycle_size <= 0 or first_sequence is None:
        return max(0, cycle_size)
    return max(0, cycle_size - (first_sequence - 1))


def prorated_fee(enrollment, *, cycle_size, first_sequence, group=None):
    """
    The amount due for this student's *first* cycle in the group, pro-rated
    for a mid-cycle join. Full fee when ``first_sequence <= 1`` (no division,
    so a full-cycle student never picks up a rounding artefact).

    Pro-ration applies on top of a symbolic/custom fee too: ``custom_fee`` is
    read as "this student's price for a full cycle", and a late joiner pays
    their fraction of it exactly like anyone paying the standard fee would.
    """
    fee = base_fee(enrollment, group)
    if fee <= 0 or cycle_size <= 0:
        return ZERO
    remaining = entitled_sessions(cycle_size=cycle_size, first_sequence=first_sequence)
    if remaining >= cycle_size:
        return fee
    return to_money(fee * Decimal(remaining) / Decimal(cycle_size))
