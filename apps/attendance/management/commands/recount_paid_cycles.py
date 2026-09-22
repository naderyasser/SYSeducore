"""
Recount ``sessions_attended`` on every paid payment of an open cycle with the
payment-date rule (absences before ``paid_on`` do not count).

The rule applies by itself whenever a payment is recounted — at the student's
next accepted scan, or when it is paid — but a student whose stored count
already reached the cycle's total because of pre-payment absences is turned
away at the gate *before* any recount happens. This brings every open paid
cycle in line once.

Dry run by default: prints what would change. ``--apply`` writes.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.attendance.entitlement import (
    _consumed_sessions, first_consumed_session, paid_from,
)
from apps.payments.models import Payment


class Command(BaseCommand):
    help = 'Recount paid open-cycle payments with the payment-date absence rule (dry run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='write the new counts')

    def handle(self, *args, apply=False, **options):
        payments = (
            Payment.objects.filter(status='paid', cycle__isnull=False, cycle__closed_on__isnull=True)
            .select_related('student', 'group', 'cycle', 'entitlement_start_session')
        )
        changed = unblocked = 0
        with transaction.atomic():
            for p in payments:
                anchor = p.entitlement_start_session or first_consumed_session(p.student, p.cycle)
                new = _consumed_sessions(p.student, p.cycle, anchor_session=anchor,
                                         absences_from=paid_from(p)) if anchor else 0
                if new == p.sessions_attended:
                    continue
                changed += 1
                was_blocked = p.sessions_attended >= p.sessions_total
                if was_blocked and new < p.sessions_total:
                    unblocked += 1
                self.stdout.write(
                    f'payment {p.pk} · student {p.student_id} · group {p.group_id}: '
                    f'{p.sessions_attended} -> {new} / {p.sessions_total}'
                    + (' (was blocked, now allowed)' if was_blocked and new < p.sessions_total else '')
                )
                if apply:
                    p.sessions_attended = new
                    p.save(update_fields=['sessions_attended'])
        verb = 'updated' if apply else 'would update'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {changed} payment(s); {unblocked} student-group pair(s) unblocked'
            + ('' if apply else ' — dry run, re-run with --apply to write')
        ))
