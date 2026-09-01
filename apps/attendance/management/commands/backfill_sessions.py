"""
Report — and optionally recover — scheduled lessons that were never recorded.

``auto_mark_absent_sessions`` materialises a ``Session`` only for *today*, so
any window in which the worker was not consuming costs those days their rows
permanently. This centre lost roughly half of every day's lessons through late
August that way, which is why a full month reported three or four sessions
instead of eight: the cycles were counting rows that had never been written.

Creating a lesson retroactively changes what students owe and what teachers are
paid, so this is a deliberate, supervised action rather than something the beat
does quietly in the background. It reports by default and only writes with
``--apply``.

No attendance is invented. Only the ``Session`` is created; who was in the room
is left blank, because a day nobody scanned is a day we cannot honestly mark
anyone absent for.

    python manage.py backfill_sessions --from 2026-08-18 --to 2026-08-31
    python manage.py backfill_sessions --from 2026-08-18 --to 2026-08-31 --apply
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.attendance.models import Session
from apps.teachers.cycles import assign_to_cycle
from apps.teachers.models import Group

WEEKDAY_NAMES = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday',
]


class Command(BaseCommand):
    help = 'Report (or with --apply, create) scheduled sessions that were never recorded.'

    def add_arguments(self, parser):
        parser.add_argument('--from', dest='date_from', required=True,
                            help='First day to check (YYYY-MM-DD).')
        parser.add_argument('--to', dest='date_to', required=True,
                            help='Last day to check (YYYY-MM-DD).')
        parser.add_argument('--group', dest='group_id', type=int, default=None,
                            help='Restrict to a single group id.')
        parser.add_argument('--apply', action='store_true',
                            help='Actually create the missing sessions.')

    def handle(self, *args, **options):
        try:
            start = date.fromisoformat(options['date_from'])
            end = date.fromisoformat(options['date_to'])
        except ValueError as exc:
            raise CommandError(f'Bad date: {exc}')
        if end < start:
            raise CommandError('--to is before --from')

        today = timezone.localdate()
        if end >= today:
            # Today is the live task's job, and a future day has not happened.
            end = today - timedelta(days=1)
            self.stdout.write(self.style.WARNING(
                f'Range trimmed to {end} — today and later are left to the scheduler.'
            ))
        if end < start:
            raise CommandError('Nothing to check once today is excluded.')

        groups = Group.objects.filter(is_active=True, deleted_at__isnull=True)
        if options['group_id']:
            groups = groups.filter(pk=options['group_id'])
        groups = list(groups.prefetch_related('schedules__room'))

        missing = []
        day = start
        while day <= end:
            day_name = WEEKDAY_NAMES[day.weekday()]
            existing = set(
                Session.objects.filter(session_date=day)
                .values_list('group_id', flat=True)
            )
            for group in groups:
                if group.group_id in existing:
                    continue
                if timezone.localtime(group.created_at).date() > day:
                    continue
                entry = group.get_schedule_for_day(day_name)
                if entry is None or not entry.start_time:
                    continue
                missing.append((day, group))
            day += timedelta(days=1)

        if not missing:
            self.stdout.write(self.style.SUCCESS('No missing sessions in that range.'))
            return

        by_day = {}
        for d, g in missing:
            by_day.setdefault(d, []).append(g)
        for d in sorted(by_day):
            self.stdout.write(f'{d} ({d.strftime("%A")}): {len(by_day[d])} missing')

        self.stdout.write('')
        self.stdout.write(f'Total missing sessions: {len(missing)}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                'Dry run — nothing written. Re-run with --apply to create them.'
            ))
            return

        created = 0
        with transaction.atomic():
            for d, group in missing:
                session, was_created = Session.objects.get_or_create(
                    group=group, session_date=d,
                    defaults={'teacher_attended': False},
                )
                if was_created:
                    assign_to_cycle(session)
                    created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Created {created} session(s). No attendance was written for them.'
        ))
