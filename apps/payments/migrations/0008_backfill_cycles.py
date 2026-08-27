"""
Backfill ``GroupCycle`` from the old calendar-month billing history, and
link every existing ``Payment``/``Session`` row to a (legacy) cycle.

Safe to run on an empty database (a fresh install / the test suite) — the
loops below simply have nothing to iterate. On a populated database this is
the one-time bridge from "billing by calendar month" to "billing by
session-counted cycle": every historical ``(group, month)`` bucket becomes
one ``GroupCycle(is_legacy=True)``, and one fresh, real cycle is opened per
still-active group so ``roll_group_cycles`` (apps.attendance.tasks) has
something to continue from on its next run.

MUST be dry-run against a copy of production data before this migration is
applied there — see the plan's migration section for the verification
checklist (per-group/month cycle counts, paid_on spot-checks against
payment_date in Africa/Cairo local time).
"""
from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def _month_bounds(month_date):
    start = month_date.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end - timedelta(days=1)


def backfill(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    Session = apps.get_model('attendance', 'Session')
    Attendance = apps.get_model('attendance', 'Attendance')
    Group = apps.get_model('teachers', 'Group')
    GroupCycle = apps.get_model('teachers', 'GroupCycle')

    # ── 1. One legacy GroupCycle per (group, month) that ever had a Payment ──
    months_by_group = {}
    for group_id, month in (
        Payment.objects.filter(cycle__isnull=True)
        .order_by('group_id', 'month')
        .values_list('group_id', 'month')
        .distinct()
    ):
        months_by_group.setdefault(group_id, []).append(month)

    groups_by_id = {g.pk: g for g in Group.objects.all()}

    for group_id, months in months_by_group.items():
        group = groups_by_id.get(group_id)
        sessions_planned = (getattr(group, 'sessions_per_month', 0) or 4) if group else 4
        existing_max = (
            GroupCycle.objects.filter(group_id=group_id)
            .order_by('-index').values_list('index', flat=True).first()
        ) or 0

        for offset, month in enumerate(sorted(months), start=1):
            start, end = _month_bounds(month)
            cycle = GroupCycle.objects.create(
                group_id=group_id,
                index=existing_max + offset,
                sessions_planned=sessions_planned,
                started_on=start,
                closed_on=end,
                is_legacy=True,
            )

            payments_qs = Payment.objects.filter(
                group_id=group_id, month=month, cycle__isnull=True,
            )
            for payment in payments_qs:
                cairo_date = (
                    timezone.localtime(payment.payment_date).date()
                    if payment.payment_date else None
                )
                payment.cycle_id = cycle.pk
                payment.paid_on = cairo_date
                payment.save(update_fields=['cycle', 'paid_on'])

            sessions_qs = list(
                Session.objects.filter(
                    group_id=group_id, session_date__gte=start, session_date__lte=end,
                    cycle__isnull=True,
                ).order_by('session_date', 'session_id')
            )
            seq = 0
            for session in sessions_qs:
                session.cycle_id = cycle.pk
                if not session.is_cancelled:
                    seq += 1
                    session.sequence_in_cycle = seq
                else:
                    session.sequence_in_cycle = None
                session.save(update_fields=['cycle', 'sequence_in_cycle'])

            # Entitlement anchor: this student's first non-cancelled
            # attendance within the cycle, if any.
            for payment in payments_qs.filter(cycle_id=cycle.pk):
                first_att = (
                    Attendance.objects.filter(
                        student_id=payment.student_id,
                        session__cycle_id=cycle.pk,
                        session__is_cancelled=False,
                    )
                    .exclude(status='absent')
                    .order_by('session__sequence_in_cycle')
                    .select_related('session')
                    .first()
                )
                if first_att is not None:
                    payment.entitlement_start_session_id = first_att.session_id
                    payment.entitlement_start_seq = first_att.session.sequence_in_cycle
                    payment.save(update_fields=[
                        'entitlement_start_session', 'entitlement_start_seq',
                    ])

    # ── 2. Open one fresh (non-legacy) cycle per still-active group ─────────
    for group in Group.objects.filter(is_active=True, deleted_at__isnull=True):
        if GroupCycle.objects.filter(group_id=group.pk, closed_on__isnull=True).exists():
            continue
        last_index = (
            GroupCycle.objects.filter(group_id=group.pk)
            .order_by('-index').values_list('index', flat=True).first()
        ) or 0
        GroupCycle.objects.create(
            group_id=group.pk,
            index=last_index + 1,
            sessions_planned=group.sessions_per_month or 4,
        )


def noop_reverse(apps, schema_editor):
    """
    Reversal only needs to undo what forward *wrote onto other tables* —
    the GroupCycle rows it created disappear on their own once the model
    itself is removed by an earlier migration's reverse, but Payment/Session
    FKs pointing at them must be cleared first or the delete would cascade
    oddly under PROTECT.
    """
    GroupCycle = apps.get_model('teachers', 'GroupCycle')
    Payment = apps.get_model('payments', 'Payment')
    Session = apps.get_model('attendance', 'Session')

    legacy_ids = list(GroupCycle.objects.filter(is_legacy=True).values_list('pk', flat=True))
    Payment.objects.filter(cycle_id__in=legacy_ids).update(
        cycle=None, paid_on=None, entitlement_start_session=None, entitlement_start_seq=None,
    )
    Session.objects.filter(cycle_id__in=legacy_ids).update(cycle=None, sequence_in_cycle=None)
    GroupCycle.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0007_cycle_billing_fields'),
        ('attendance', '0007_cycle_billing_fields'),
        ('teachers', '0013_cycle_billing_fields'),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
