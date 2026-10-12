"""
Group-cycle helpers — session-based billing operates on ``GroupCycle`` rather
than on calendar months. This module owns every write to a cycle's sessions
and to ``Session.sequence_in_cycle``.

A cycle is "open" while ``started_on`` is set and ``closed_on`` is null.
Closing a cycle (once its ``sessions_planned`` non-cancelled sessions have
happened) and opening the next one is the job of
``apps.attendance.tasks.roll_group_cycles`` — this module only manages the
per-session bookkeeping (assignment, renumbering) that keeps a cycle's
sequence numbers correct as sessions are created or cancelled.
"""
from django.db import transaction

from .models import GroupCycle


def pick_current(cycles):
    """
    The group's current cycle among its unclosed ``cycles``: the running one
    (started), else the *earliest* reserved one — never a later cycle a
    package reserved ahead of it. Taking the highest index (as this module
    used to) handed a reserved package cycle to the gate, to the next lesson
    and to the roll-over in place of the cycle actually running.
    """
    cycles = list(cycles)
    started = [c for c in cycles if c.started_on is not None]
    if started:
        return max(started, key=lambda c: c.index)
    return min(cycles, key=lambda c: c.index) if cycles else None


def current_cycles(group_ids):
    """``{group_id: current cycle}`` for many groups in one query (no creation)."""
    by_group = {}
    for cycle in GroupCycle.objects.filter(group_id__in=list(group_ids), closed_on__isnull=True):
        by_group.setdefault(cycle.group_id, []).append(cycle)
    return {group_id: pick_current(cycles) for group_id, cycles in by_group.items()}


def open_cycle_for(group):
    """
    Return the group's current cycle (see :func:`pick_current`), creating one
    if none exists.

    The new cycle starts "reserved" (``started_on=None``) until
    :func:`assign_to_cycle` sees its first real session.
    """
    cycle = pick_current(GroupCycle.objects.filter(group=group, closed_on__isnull=True))
    if cycle is not None:
        return cycle

    last_index = (
        GroupCycle.objects.filter(group=group).order_by('-index')
        .values_list('index', flat=True).first()
    ) or 0
    return GroupCycle.objects.create(
        group=group,
        index=last_index + 1,
        sessions_planned=group.sessions_per_month or 4,
    )


def _renumber(cycle):
    """
    Number a cycle's non-cancelled sessions 1..N **in date order**, and clear
    the number on every cancelled one. No closed-cycle guard — internal.
    """
    from apps.attendance.models import Session

    live = list(
        Session.objects.select_for_update()
        .filter(cycle=cycle, is_cancelled=False)
        .order_by('session_date', 'session_id')
    )
    for seq, session in enumerate(live, start=1):
        if session.sequence_in_cycle != seq:
            session.sequence_in_cycle = seq
            session.save(update_fields=['sequence_in_cycle'])

    cancelled_ids = list(
        Session.objects.filter(cycle=cycle, is_cancelled=True)
        .exclude(sequence_in_cycle=None)
        .values_list('session_id', flat=True)
    )
    if cancelled_ids:
        Session.objects.filter(session_id__in=cancelled_ids).update(sequence_in_cycle=None)


def assign_to_cycle(session):
    """
    Attach ``session`` to its group's open cycle and (re)number the cycle.

    The sequence is derived from **date order**, not insertion order: a
    session backfilled for an earlier date must not land after ones already
    recorded, or the entitlement anchor (which is a sequence number) would
    point at the wrong lesson. Renumbering the whole cycle is cheap — a cycle
    is 4 to 8 sessions.

    A cancelled session is attached (for bookkeeping / display) but always
    gets ``sequence_in_cycle=None`` — it must never consume entitlement.
    Idempotent: calling it twice on the same session is safe.
    """
    with transaction.atomic():
        cycle = open_cycle_for(session.group)
        if cycle.started_on is None or session.session_date < cycle.started_on:
            cycle.started_on = session.session_date
            cycle.save(update_fields=['started_on'])

        session.cycle = cycle
        session.save(update_fields=['cycle'])
        _renumber(cycle)
        session.refresh_from_db(fields=['sequence_in_cycle'])
    return session


def renumber_cycle(cycle):
    """
    Re-assign ``sequence_in_cycle`` over a cycle's non-cancelled sessions, in
    date order. Called after a session is cancelled/uncancelled so the
    remaining sequence stays contiguous starting at 1.

    Refuses to touch a closed cycle — its billing has already been settled,
    so rewriting history there must go through an explicit exception/credit
    instead of a silent renumber.
    """
    if cycle.closed_on is not None:
        raise ValueError('لا يمكن تعديل حصص دورة مغلقة — استخدم استثناء بدلاً من ذلك')

    with transaction.atomic():
        _renumber(cycle)


def ensure_next(group, count=1, student=None):
    """
    The ``count`` reserved (not-yet-started) cycles that follow ``group``'s
    current one, for a multi-cycle package purchase — reusing those already
    reserved, creating only what is missing. Returns them in order.
    """
    current = open_cycle_for(group)
    # Cycles are the group's, not the buyer's: a second package bought while
    # the first one's cycles are still waiting uses those same cycles — it
    # used to stack new ones after them, so its prepaid cycle 2 was really
    # the group's cycle 3.
    # ``student``'s own earlier package is skipped: a cycle they already
    # prepaid cannot be sold to them twice.
    reserved = GroupCycle.objects.filter(
        group=group, closed_on__isnull=True, started_on__isnull=True,
        index__gt=current.index,
    )
    if student is not None:
        reserved = reserved.exclude(payments__student=student)
    reserved = list(reserved.order_by('index')[:count])
    last_index = (
        GroupCycle.objects.filter(group=group).order_by('-index')
        .values_list('index', flat=True).first()
    ) or 0
    created = []
    for offset in range(1, count - len(reserved) + 1):
        created.append(GroupCycle(
            group=group,
            index=last_index + offset,
            sessions_planned=group.sessions_per_month or 4,
        ))
    return reserved + (GroupCycle.objects.bulk_create(created) if created else [])
