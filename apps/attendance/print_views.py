"""
Printable pages for the attendance app — kept out of ``views.py`` (764+
lines already) since these are rendering-only, standalone HTML documents
that don't extend ``base.html``.
"""
from datetime import timedelta

from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts.decorators import supervisor_required
from apps.teachers.models import Group

from .grids import build_group_attendance_grid


@supervisor_required
def group_roster_print(request, group_id):
    """
    كشف حضور قابل للطباعة — عمود لكل تاريخ حصة مُجدوَل حتى اليوم، بما فيها
    التواريخ التي لم يُسجَّل فيها أي حضور (السكانر كان معطلاً / لم يمسح أحد)،
    ليدخل بها المشرف القاعة وينادي بالأسماء.

    ``?from=YYYY-MM-DD&to=YYYY-MM-DD`` — تفترض افتراضيًا آخر 30 يومًا حتى اليوم.
    """
    group = get_object_or_404(
        Group.objects.select_related('teacher').prefetch_related('schedules__room'),
        pk=group_id,
    )

    today = timezone.localdate()
    date_from = today - timedelta(days=30)
    date_to = today

    raw_from = request.GET.get('from')
    raw_to = request.GET.get('to')
    if raw_from:
        try:
            date_from = timezone.datetime.fromisoformat(raw_from).date()
        except ValueError:
            pass
    if raw_to:
        try:
            date_to = timezone.datetime.fromisoformat(raw_to).date()
        except ValueError:
            pass
    # A printed roster never needs future dates — "up to today" is the
    # whole point (calling names for sessions that already happened).
    date_to = min(date_to, today)

    grid = build_group_attendance_grid(group, date_from, date_to, include_expected=True)

    # Wide ranges get split into several tables (name column repeated)
    # instead of shrinking the font past legibility. Each chunk carries its
    # own columns AND every row's cells already zipped to them, so the
    # template never needs to index two parallel lists by the same offset.
    columns = grid['columns']
    chunk_size = 14
    n_chunks = max(1, -(-len(columns) // chunk_size))  # ceil division

    chunks = []
    for i in range(n_chunks):
        start, end = i * chunk_size, (i + 1) * chunk_size
        chunk_rows = [
            {'student': row['student'], 'cells': row['cells'][start:end]}
            for row in grid['rows']
        ]
        chunks.append({'columns': columns[start:end], 'rows': chunk_rows})

    context = {
        'group': group,
        'date_from': date_from,
        'date_to': date_to,
        'chunks': chunks,
        'printed_at': timezone.localtime(),
    }
    return render(request, 'attendance/roster_print.html', context)
