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


def open_cycle_for(group):
    """
    Return the group's open cycle, creating one if none exists.

    The new cycle starts "reserved" (``started_on=None``) until
    :func:`assign_to_cycle` sees its first real session.
    """
    cycle = (
        GroupCycle.objects
        .filter(group=group, closed_on__isnull=True)
        .order_by('-index')
        .first()
    )
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


def assign_to_cycle(session):
    """
    Attach ``session`` to its group's open cycle and set its
    ``sequence_in_cycle``.

    A cancelled session is attached (for bookkeeping / display) but always
    gets ``sequence_in_cycle=None`` — it must never consume a student's
    entitlement. Idempotent: calling it twice on the same session is safe.
    """
    with transaction.atomic():
        cycle = open_cycle_for(session.group)
        if cycle.started_on is None:
            cycle.started_on = session.session_date
            cycle.save(update_fields=['started_on'])

        session.cycle = cycle
        if session.is_cancelled:
            session.sequence_in_cycle = None
        else:
            session.sequence_in_cycle = (
                cycle.sessions.filter(is_cancelled=False)
                .exclude(pk=session.pk)
                .count() + 1
            )
        session.save(update_fields=['cycle', 'sequence_in_cycle'])
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

    from apps.attendance.models import Session

    with transaction.atomic():
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


def ensure_next(group, count=1):
    """
    Pre-create ``count`` reserved (not-yet-started) future cycles for
    ``group``, for a multi-cycle package purchase. Returns the created
    :class:`GroupCycle` list in order.
    """
    last_index = (
        GroupCycle.objects.filter(group=group).order_by('-index')
        .values_list('index', flat=True).first()
    ) or 0
    created = []
    for offset in range(1, count + 1):
        created.append(GroupCycle(
            group=group,
            index=last_index + offset,
            sessions_planned=group.sessions_per_month or 4,
        ))
    return GroupCycle.objects.bulk_create(created)
