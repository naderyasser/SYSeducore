"""
Attendance grid builder — shared by the group detail page (apps.teachers)
and the printable roster (apps.attendance.print_views).

Builds a "students × sessions" matrix in a fixed, small number of queries,
independent of the number of students or sessions in the range.
"""
from datetime import timedelta

from django.db.models import Min
from django.utils import timezone

from .models import Attendance, ExceptionRecord, Session

CELL_NOT_ENROLLED = 'not_enrolled'
CELL_CANCELLED = 'cancelled'
CELL_UNRECORDED = 'unrecorded'
CELL_NO_RECORD = 'no_record'


def build_group_attendance_grid(group, date_from, date_to, include_expected=False):
    """
    Returns ``{'columns': [...], 'rows': [...]}`` for ``group`` over
    ``[date_from, date_to]`` (inclusive).

    Each column is ``{'date': date, 'is_cancelled': bool, 'unrecorded': bool}``.
    Each row is ``{'student', 'enrollment', 'first_attended', 'anchor_date',
    'cells': [...]}`` where ``cells[i]`` is a state string aligned with
    ``columns[i]``: ``present``/``late``/``absent``/``exception`` (real
    attendance statuses), or one of the module constants above.

    ``include_expected=False`` (default): columns are exactly the real
    ``Session`` rows in range — honest about what the system actually has
    evidence for.
    ``include_expected=True``: additionally synthesizes a column for every
    date in range whose weekday matches the group's weekly schedule but has
    no ``Session`` row — marked ``unrecorded`` (the scanner was off, or
    nobody scanned). Used by the printable roster, where a supervisor needs
    to see — and manually fill in — exactly those gaps.

    Exactly 4 queries total, regardless of student/session count.
    """
    from apps.students.models import StudentGroupEnrollment

    # Q1 — active enrollments (one row per student)
    enrollments = list(
        StudentGroupEnrollment.objects
        .filter(group=group, is_active=True, student__deleted_at__isnull=True)
        .select_related('student')
        .order_by('student__full_name')
    )

    # Q2 — real Session rows in range
    sessions = list(
        Session.objects.filter(
            group=group, session_date__gte=date_from, session_date__lte=date_to,
        )
        .order_by('session_date')
        .values('session_id', 'session_date', 'is_cancelled', 'cancellation_reason')
    )
    session_ids = [s['session_id'] for s in sessions]
    real_dates = {s['session_date'] for s in sessions}

    columns = [
        {'session_id': s['session_id'], 'date': s['session_date'],
         'is_cancelled': s['is_cancelled'], 'unrecorded': False,
         'cancellation_reason': s['cancellation_reason']}
        for s in sessions
    ]

    if include_expected:
        scheduled_weekdays = {
            entry.day_of_week for entry in group.get_schedule_entries()
        }
        # Python weekday name matching WEEK_DAYS convention used elsewhere
        # (strftime('%A') gives the English day name, matching DAYS_CHOICES).
        day = date_from
        expected_dates = []
        while day <= date_to:
            if day.strftime('%A') in scheduled_weekdays and day not in real_dates:
                expected_dates.append(day)
            day += timedelta(days=1)
        for d in expected_dates:
            columns.append({
                'session_id': None, 'date': d,
                'is_cancelled': False, 'unrecorded': True,
            })
        columns.sort(key=lambda c: c['date'])

    # Q3 — the full attendance matrix in one flat query
    cells_by_key = {}
    locked_keys = set()
    exception_keys = {}   # (student, session) -> (exception_record_id, supervisor name)
    for student_id, session_id, status, exception_record_id, supervisor, note in (
        Attendance.objects.filter(session_id__in=session_ids)
        .values_list('student_id', 'session_id', 'status', 'exception_record_id',
                     'supervisor__username', 'note')
    ):
        cells_by_key[(student_id, session_id)] = status
        if status == 'exception':
            exception_keys[(student_id, session_id)] = (exception_record_id, supervisor, note)
        # A row linked to an approved ExceptionRecord is managed by
        # grant/revoke — the grid must not offer to overwrite it. A manual
        # "عذر" (same status, no record) stays editable.
        if exception_record_id is not None:
            locked_keys.add((student_id, session_id))

    # Q4 — first ACTUAL attendance date per student (present/late/exception)
    # .order_by() is mandatory: Attendance.Meta.ordering = ['-scan_time']
    # would otherwise join the GROUP BY and return one row per scan.
    first_attended = dict(
        Attendance.objects
        .filter(session__group=group, status__in=('present', 'late', 'exception'))
        .values_list('student_id')
        .annotate(first=Min('session__session_date'))
        .order_by()
        .values_list('student_id', 'first')
    )

    # Payment/entitlement data is deliberately left to the caller
    # (group_detail resolves it itself) so this module stays focused on
    # the grid shape alone.

    # Q5 (only when there are any) — why each «عذر/استثناء» cell is one: the
    # approved ExceptionRecord's reason, or "عذر يدوي" and who marked it.
    cell_notes = {}
    if exception_keys:
        records = {
            r.exception_id: r
            for r in ExceptionRecord.objects.filter(
                exception_id__in=[v[0] for v in exception_keys.values() if v[0]]
            ).select_related('approved_by')
        }
        for key, (record_id, supervisor, note) in exception_keys.items():
            rec = records.get(record_id)
            if rec is not None:
                reason = rec.get_reason_type_display().split(' – ')[0]
                if rec.custom_reason:
                    reason += f': {rec.custom_reason}'
                who = rec.approved_by.username if rec.approved_by_id else ''
                kind = rec.get_exception_type_display().split(' — ')[0]
                cell_notes[key] = f'{kind} — {reason}' + (f' (وافق: {who})' if who else '')
            else:
                cell_notes[key] = f'عذر — {note or "بدون سبب مكتوب"}' + (f' (سجّله: {supervisor})' if supervisor else '')

    rows = []
    for enr in enrollments:
        sid = enr.student_id
        enrolled_date = timezone.localtime(enr.enrolled_at).date()
        first_att = first_attended.get(sid)
        anchor = min(enrolled_date, first_att) if first_att else enrolled_date

        row_cells = []
        locked_cells = []
        row_notes = []
        for col in columns:
            if col['unrecorded']:
                state = CELL_UNRECORDED
            elif col['is_cancelled']:
                state = CELL_CANCELLED
            elif col['date'] < anchor:
                state = CELL_NOT_ENROLLED
            else:
                state = cells_by_key.get((sid, col['session_id']), CELL_NO_RECORD)
            row_cells.append(state)
            locked_cells.append((sid, col['session_id']) in locked_keys)
            row_notes.append(cell_notes.get((sid, col['session_id']), ''))

        rows.append({
            'student': enr.student,
            'enrollment': enr,
            'enrolled_date': enrolled_date,
            'first_attended': first_att,
            'anchor_date': anchor,
            'cells': row_cells,
            'locked': locked_cells,
            'notes': row_notes,
        })

    # One readable list under the grid: every excuse and cancelled lesson
    # in range with its reason — a coloured cell alone explained nothing.
    by_session = {c['session_id']: c['date'] for c in columns if c['session_id']}
    students = {enr.student_id: enr.student for enr in enrollments}
    notes = [
        {'date': by_session.get(session_id), 'student': students.get(sid), 'text': text, 'kind': 'exception'}
        for (sid, session_id), text in cell_notes.items() if sid in students
    ]
    notes += [
        {'date': c['date'], 'student': None, 'kind': 'cancelled',
         'text': 'حصة ملغية — ' + (c['cancellation_reason'] or 'بدون سبب مكتوب')}
        for c in columns if c['is_cancelled']
    ]
    notes.sort(key=lambda n: (n['date'] or date_from, n['kind']))
    return {'columns': columns, 'rows': rows, 'notes': notes}
