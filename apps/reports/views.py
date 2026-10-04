"""
Reports app views.

Authorization model (SEC-07 / AUTH-09…AUTH-11)
----------------------------------------------
There used to be a "report password" gate here (``REPORTS_PASSWORD``,
``report_password_required``). It was inert: the decorator returned
immediately for any authenticated user, and every view it decorated was also
``@login_required`` — so the password branch was unreachable and the
"protected" financial reports were open to every role. The gate, its
hardcoded ``888888`` default and the three views that served it have been
removed; these reports are now protected by the real role decorators:

* ``dashboard`` / ``attendance_report`` — any authenticated user; cumulative
  money figures (``show_financials``) are computed and shown to admins only.
* ``payment_report`` — supervisor or admin (desk collection work); the same
  ``show_financials`` gate hides its aggregate totals from non-admins.
* ``tsfya`` / ``financial_report`` — admin only (centre-wide revenue).
* ``activity_log`` — admin only (it holds usernames and IP addresses).
* recycle bin: view + restore are supervisor, permanent delete + empty are
  admin.
"""
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.contrib import messages

from config import feature_lock
from config.feature_lock import locked_feature
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.template.defaultfilters import date as date_filter
from django.utils.dateparse import parse_date

from apps.accounts.decorators import (
    admin_required,
    ajax_admin_required,
    ajax_supervisor_required,
    supervisor_required,
)
from apps.attendance.models import ActivityLog, Attendance, Session
from apps.payments.models import Payment
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import WEEK_DAYS_AR, Group, Room, Teacher

logger = logging.getLogger(__name__)


# ==================== Shared helpers ====================

#: The word an admin has to type before the recycle bin can be emptied.
RECYCLE_EMPTY_CONFIRM = 'تفريغ'

DAY_NAMES = {
    0: 'Monday', 1: 'Tuesday', 2: 'Wednesday',
    3: 'Thursday', 4: 'Friday', 5: 'Saturday', 6: 'Sunday',
}


def AttendanceService_get_day_name(day=None):
    """
    Weekday name of ``day`` (default: **today in the centre's timezone**).

    Kept under its historical name because other modules import it.
    """
    day = day or timezone.localdate()
    return DAY_NAMES.get(day.weekday(), '')


def add_months(day, count):
    """First day of the month ``count`` months after ``day``'s month."""
    index = day.year * 12 + (day.month - 1) + count
    return date(index // 12, index % 12 + 1, 1)


def parse_month_param(value):
    """
    Parse a ``?month=`` parameter into the first day of that month.

    Accepts ``YYYY-MM`` (what ``<input type="month">`` submits) and
    ``YYYY-MM-DD``; returns ``None`` when the value cannot be understood.

    This exists because ``month`` is a ``DateField`` and the report used to
    filter it with ``month__startswith=...``. Pattern lookups skip value
    coercion, so the SQL became ``"payments"."month" LIKE '2026-02%'`` —
    which SQLite tolerates (dates are text there) and PostgreSQL rejects
    outright with ``operator does not exist: date ~~ unknown``. Callers use
    the returned date with a half-open ``[month, next month)`` range instead
    (BUG-06).
    """
    if not value:
        return None
    raw = str(value).strip()
    for fmt in ('%Y-%m', '%Y-%m-%d', '%Y/%m'):
        try:
            return datetime.strptime(raw, fmt).date().replace(day=1)
        except ValueError:
            continue
    return None


def _reportable_payments():
    """
    Payments the money reports count. A due that belongs to a student or
    group in the recycle bin — with nothing collected on it — is not owed to
    anyone any more; it inflated "المستحق"/"المتبقي" while the desk page and
    the dashboard's pending list already hid it. Anything actually collected
    stays: that money was taken.
    """
    return Payment.objects.exclude(
        (Q(student__deleted_at__isnull=False) | Q(group__deleted_at__isnull=False))
        & Q(amount_paid=0)
    )


def _month_filter(queryset, month_start, field='month'):
    """Restrict ``queryset`` to a single calendar month, range-style."""
    return queryset.filter(**{
        f'{field}__gte': month_start,
        f'{field}__lt': add_months(month_start, 1),
    })


def _rate(part, whole):
    return (part / whole * 100) if whole else 0


def _parse_date_param(value):
    """
    Parse a ``?date_from=``/``?date_to=`` style GET param into a ``date``.

    Returns ``None`` for a blank/absent value and for one that does not
    parse — ``django.utils.dateparse.parse_date`` only accepts ISO
    ``YYYY-MM-DD`` (what ``<input type="date">`` submits) and returns
    ``None`` on anything else, rather than raising. Filtering with the raw
    string instead used to raise ``ValidationError`` inside the ORM for a
    malformed value (e.g. a hand-edited ``20/8/2026``), a 500 with no
    exception middleware to catch it (unvalidated-get-filters-500).
    """
    if not value:
        return None
    return parse_date(str(value).strip())


def _parse_int_param(value):
    """Parse a ``?group=``/``?teacher=``/``?user=`` id param, or ``None``."""
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ==================== Dashboard ====================

@login_required
def dashboard(request):
    """
    Professional Dashboard with comprehensive statistics, charts,
    schedule widget, and activity log.

    Everything below is resolved in the centre's local timezone: ``today`` is
    ``timezone.localdate()`` and the "is this session running now?" comparison
    uses ``timezone.localtime()``. Using ``timezone.now()`` compared local
    ``schedule_time`` values against a UTC clock, which put every status badge
    2-3 hours out of phase and made the day name disagree with the date after
    midnight Cairo (TZ-01 / TZ-02).
    """
    today = timezone.localdate()
    this_month_start = today.replace(day=1)
    current_day_name = AttendanceService_get_day_name(today)
    current_time = timezone.localtime().time()

    # ====== KEY METRICS ======
    student_totals = Student.objects.filter(is_active=True).aggregate(
        total=Count('student_id'),
        new_this_month=Count(
            'student_id', filter=Q(created_at__date__gte=this_month_start)
        ),
    )
    total_students = student_totals['total'] or 0
    new_students_this_month = student_totals['new_this_month'] or 0
    total_teachers = Teacher.objects.filter(is_active=True).count()
    total_rooms = Room.objects.filter(is_active=True).count()

    # ====== TODAY'S OVERVIEW ======
    session_totals = Session.objects.filter(
        session_date=today, group__is_active=True
    ).aggregate(
        total=Count('session_id'),
        cancelled=Count('session_id', filter=Q(is_cancelled=True)),
    )
    today_total_sessions = session_totals['total'] or 0
    today_cancelled_sessions = session_totals['cancelled'] or 0
    today_active_sessions = today_total_sessions - today_cancelled_sessions

    # ====== WEEK ATTENDANCE TREND (single grouped query) ======
    # This used to be a 4-query-per-day loop (28 queries) plus 3 more for
    # today; one GROUP BY over the same window now answers both (PERF-05).
    week_start = today - timedelta(days=6)
    per_day = defaultdict(lambda: defaultdict(int))
    status_rows = (
        Attendance.objects
        .filter(session__session_date__gte=week_start,
                session__session_date__lte=today)
        .values('session__session_date', 'status')
        .annotate(n=Count('attendance_id'))
        .order_by()
    )
    for row in status_rows:
        per_day[row['session__session_date']][row['status']] = row['n']

    week_attendance_data = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        counts = per_day[day]
        present = counts['present']
        late = counts['late']
        absent = counts['absent']
        total = present + late + absent
        week_attendance_data.append({
            'date': WEEK_DAYS_AR.get(DAY_NAMES[day.weekday()], day.strftime('%a')),
            'full_date': day.strftime('%Y-%m-%d'),
            'present': present,
            'late': late,
            'absent': absent,
            'rate': round(_rate(present + late, total), 1),
        })

    today_counts = per_day[today]
    # 'late' is a real, reachable status again — check_strict_time records the
    # 1-10 minute window as 'late' — so this counter is no longer always zero
    # (DATA-17).
    today_present = today_counts['present']
    today_late = today_counts['late']
    today_absent = today_counts['absent']
    today_total_attendance = today_present + today_late + today_absent
    today_attendance_rate = _rate(today_present + today_late, today_total_attendance)

    absent_today = Attendance.objects.filter(
        session__session_date=today, status='absent'
    ).select_related('student', 'session__group')[:5]

    # ====== FINANCIAL SUMMARY ======
    # Cumulative centre-wide totals — admin only (AUTH-09). The aggregate
    # must not even be computed for a non-admin: removing the template
    # block alone would still leak the numbers into the page context.
    show_financials = request.user.can_see_financials()
    month_total_due = month_total_paid = month_remaining = collection_rate = None
    if show_financials:
        # Half-open [this_month, next_month) range — a plain ``month__gte`` also
        # swept in every future-dated row that ``roll_group_cycles`` bulk
        # creates for groups whose cycle already closed, so "this month"
        # kept growing by every upcoming month's dues (dashboard-month-gte-future-payments).
        month_totals = _month_filter(_reportable_payments(), this_month_start).aggregate(
            total_due=Sum('amount_due'),
            total_paid=Sum('amount_paid'),
        )
        month_total_due = month_totals['total_due'] or 0
        month_total_paid = month_totals['total_paid'] or 0
        month_remaining = month_total_due - month_total_paid
        collection_rate = _rate(month_total_paid, month_total_due)

    # Soft-deleted students/groups are excluded from both the count and the
    # list below them — they used to share nothing, so a student who had
    # been moved to the recycle bin still padded the "مدفوعات معلقة" badge
    # and kept reappearing in the list underneath it forever
    # (pending-payments-soft-delete-leak). Both now read the same
    # month-scoped, soft-delete-excluding queryset.
    pending_payments_qs = _month_filter(
        Payment.objects.filter(
            status__in=['unpaid', 'partial'],
            student__deleted_at__isnull=True,
            group__deleted_at__isnull=True,
        ),
        this_month_start,
    )
    pending_payments_count = pending_payments_qs.count()
    pending_payments_list = pending_payments_qs.select_related(
        'student', 'group'
    ).order_by('-month')[:5]

    # Exclude exempt (0 ج.م, no payment_date) rows and NULL payment_date so
    # PostgreSQL's "NULLs first" DESC ordering doesn't fill the panel with
    # zero-fee waivers instead of the day's real collections
    # (recent-payments-null-payment-date-first).
    recent_payments = Payment.objects.select_related('student', 'group').filter(
        status__in=['paid', 'partial'], is_exempt=False, payment_date__isnull=False
    ).order_by('-payment_date')[:5]

    # ====== GROUPS: today's schedule + enrolment health ======
    # One query for the groups, one for their schedules (prefetch) and one
    # grouped query for the enrolment counts — instead of a per-group
    # ``GroupSchedule.objects.get()`` and a second annotated groups query.
    enrolment_counts = dict(
        StudentGroupEnrollment.objects
        .filter(is_active=True, group__is_active=True)
        .values_list('group_id')
        .annotate(n=Count('id'))
        .order_by()
        .values_list('group_id', 'n')
    )
    active_groups = list(
        Group.objects.filter(is_active=True)
        .select_related('teacher')
        .prefetch_related('schedules__room')
    )
    total_active_groups = len(active_groups)

    # ====== TODAY'S SCHEDULE ======
    # ``get_schedule_entries()`` (apps.teachers.models) is the single source of
    # schedule truth: it returns one entry per weekly session from
    # ``GroupSchedule``, each carrying its own room (DATA-04).
    cancelled_today = set(
        Session.objects.filter(session_date=today, is_cancelled=True)
        .values_list('group_id', flat=True)
    )
    today_schedule = []
    for grp in active_groups:
        for entry in grp.get_schedule_entries():
            if entry.day_of_week != current_day_name:
                continue
            enrolled_count = enrolment_counts.get(grp.pk, 0)
            capacity = entry.room.capacity if entry.room else 0
            end_time = entry.get_end_time()

            session_status = 'upcoming'
            if grp.pk in cancelled_today:
                session_status = 'cancelled'
            elif current_time > end_time:
                session_status = 'completed'
            elif current_time >= entry.start_time:
                session_status = 'ongoing'

            today_schedule.append({
                'id': grp.group_id,
                'group_name': grp.group_name,
                'teacher': grp.teacher.full_name if grp.teacher else '-',
                'room': entry.room.name if entry.room else '-',
                'sort_key': entry.start_time,
                'time_start': entry.start_time.strftime('%I:%M %p'),
                'time_end': end_time.strftime('%I:%M %p'),
                'duration': entry.get_duration_display(),
                'enrolled': enrolled_count,
                'capacity': capacity,
                'utilization': _rate(enrolled_count, capacity),
                'status': session_status,
            })

    # Sort on the real time — the formatted '%I:%M %p' string sorts
    # "01:00 PM" before "09:00 AM".
    today_schedule.sort(key=lambda s: s['sort_key'])
    for slot in today_schedule:
        del slot['sort_key']
    # The "حصص اليوم" card counts the same timetable the table lists. It used
    # to count Session rows — one per group per day, and only once written —
    # so a group meeting twice today, or a lesson nobody had opened yet, made
    # the card and the table disagree (30 vs 32).
    today_total_sessions = sum(1 for s in today_schedule if s['status'] != 'cancelled')

    # ====== GROUPS STATUS ======
    groups_low_enrollment = []
    groups_high_enrollment = []
    for group in active_groups:
        enrolled = enrolment_counts.get(group.pk, 0)
        capacity = group.get_capacity()
        utilization = _rate(enrolled, capacity)

        group_info = {
            'name': group.group_name,
            'teacher': group.teacher.full_name if group.teacher else '-',
            'enrolled': enrolled,
            'capacity': capacity,
            'utilization': utilization,
        }

        if utilization < 50:
            groups_low_enrollment.append(group_info)
        elif utilization >= 90:
            groups_high_enrollment.append(group_info)

    # ====== RECENT ACTIVITY ======
    recent_attendances = Attendance.objects.select_related(
        'student', 'session__group'
    ).order_by('-scan_time')[:6]
    recent_activities = ActivityLog.objects.select_related('user').order_by('-created_at')[:10]

    context = {
        # Key Metrics
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_rooms': total_rooms,
        'total_groups': total_active_groups,
        'new_students_this_month': new_students_this_month,

        # Today's Overview
        'today_date': today,
        'today_day_name': WEEK_DAYS_AR.get(current_day_name, current_day_name),
        'today_total_sessions': today_total_sessions,
        'today_active_sessions': today_active_sessions,
        'today_cancelled_sessions': today_cancelled_sessions,
        'today_present': today_present,
        'today_late': today_late,
        'today_absent': today_absent,
        'today_total_attendance': today_total_attendance,
        'today_attendance_rate': round(today_attendance_rate, 1),
        'absent_today': absent_today,

        # Financial — per-payment desk data, visible to supervisors too.
        'pending_payments_count': pending_payments_count,
        'pending_payments_list': pending_payments_list,
        'recent_payments': recent_payments,
        'show_financials': show_financials,

        # Schedule
        'today_schedule': today_schedule,

        # Charts
        'week_attendance_json': json.dumps(week_attendance_data, ensure_ascii=False),

        # Recent Activity
        'recent_attendances': recent_attendances,
        'recent_activities': recent_activities,

        # Groups Status
        'groups_low_enrollment': groups_low_enrollment[:3],
        'groups_high_enrollment': groups_high_enrollment[:3],
    }

    # Cumulative aggregates only ever reach the context for an admin — a
    # non-admin's response has no ``month_total_due`` key at all, not just a
    # hidden template block.
    if show_financials:
        context.update({
            'month_total_due': month_total_due,
            'month_total_paid': month_total_paid,
            'month_remaining': month_remaining,
            'collection_rate': round(collection_rate, 1),
        })

    return render(request, 'reports/dashboard.html', context)


# ==================== Attendance report ====================

# Printing one of the list reports prints every filtered row, not the
# 25-row page on screen. The cap keeps a runaway "all time" print from
# building a multi-thousand-row page; the sheet says when it was cut.
PRINT_ROW_LIMIT = 3000


def _render_list_print(request, *, title, filters, stats, columns, rows, total):
    return render(request, 'reports/list_print.html', {
        'title': title,
        'filters': [f for f in filters if f],
        'stats': stats,
        'columns': columns,
        'rows': rows,
        'total': total,
        'truncated': total > len(rows),
        'printed_at': timezone.localtime(),
    })


@login_required
def attendance_report(request):
    """
    Comprehensive Attendance Report with filters and statistics
    """
    # Get filter parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    group_id = request.GET.get('group')
    status = request.GET.get('status')

    # Base queryset
    attendances = Attendance.objects.select_related(
        'student', 'session', 'session__group', 'session__group__teacher'
    ).order_by('-scan_time')

    # Apply filters — parsed first (unvalidated-get-filters-500): a
    # malformed date or id used to reach ``.filter()`` raw and raise
    # ValidationError/ValueError inside the ORM, a bare 500. An unparseable
    # value now yields no rows, matching the existing ``?month=`` contract.
    if date_from:
        date_from_parsed = _parse_date_param(date_from)
        attendances = (
            attendances.filter(session__session_date__gte=date_from_parsed)
            if date_from_parsed else attendances.none()
        )
    if date_to:
        date_to_parsed = _parse_date_param(date_to)
        attendances = (
            attendances.filter(session__session_date__lte=date_to_parsed)
            if date_to_parsed else attendances.none()
        )
    if group_id:
        group_id_parsed = _parse_int_param(group_id)
        attendances = (
            attendances.filter(session__group__group_id=group_id_parsed)
            if group_id_parsed is not None else attendances.none()
        )
    if status:
        attendances = attendances.filter(status=status)

    # Statistics — one aggregate instead of four COUNT round-trips.
    stats = attendances.aggregate(
        total=Count('attendance_id'),
        present=Count('attendance_id', filter=Q(status='present')),
        late=Count('attendance_id', filter=Q(status='late')),
        absent=Count('attendance_id', filter=Q(status='absent')),
    )

    # Group filter options
    groups = Group.objects.filter(is_active=True)

    if request.GET.get('print'):
        group_name = (
            groups.filter(group_id=_parse_int_param(group_id)).values_list('group_name', flat=True).first()
            if group_id else None
        )
        status_label = dict(Attendance.STATUS_CHOICES).get(status)
        rows = [
            [
                a.student.full_name, a.student.student_code or '',
                a.session.group.group_name, a.session.group.teacher.full_name if a.session.group.teacher else '',
                a.session.session_date.strftime('%Y-%m-%d'),
                timezone.localtime(a.scan_time).strftime('%H:%M') if a.scan_time else '',
                a.get_status_display(),
            ]
            for a in attendances[:PRINT_ROW_LIMIT]
        ]
        return _render_list_print(
            request,
            title='تقرير الحضور',
            filters=[
                f'من {date_from}' if date_from else '',
                f'إلى {date_to}' if date_to else '',
                f'المجموعة: {group_name}' if group_name else '',
                f'الحالة: {status_label}' if status_label else '',
            ],
            stats=[
                ('إجمالي السجلات', stats['total'] or 0),
                ('حاضر', stats['present'] or 0),
                ('متأخر', stats['late'] or 0),
                ('غائب', stats['absent'] or 0),
            ],
            columns=['الطالب', 'الكود', 'المجموعة', 'المدرس', 'التاريخ', 'الوقت', 'الحالة'],
            rows=rows,
            total=stats['total'] or 0,
        )

    # Pagination
    paginator = Paginator(attendances, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'total_count': stats['total'] or 0,
        'present_count': stats['present'] or 0,
        # Reachable again now that the scanner records the 1-10 minute
        # window as 'late' (DATA-17).
        'late_count': stats['late'] or 0,
        'absent_count': stats['absent'] or 0,
        'groups': groups,
        'date_from': date_from,
        'date_to': date_to,
        'selected_group': group_id,
        'selected_status': status,
    }

    return render(request, 'reports/attendance.html', context)


@supervisor_required
@locked_feature
def attendance_excel(request):
    """
    ``GET ?date_from=&date_to=&group=`` → a formatted .xlsx: per lesson,
    the teacher, the group, how many attended and how many of them paid in
    full / in part / not at all; a second sheet lists every student.
    Defaults to today. See :mod:`apps.reports.excel`.
    """
    from django.http import HttpResponse

    from .excel import build_attendance_workbook

    today = timezone.localdate()
    date_from = _parse_date_param(request.GET.get('date_from')) or today
    date_to = _parse_date_param(request.GET.get('date_to')) or date_from
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days > 366:
        date_from = date_to - timedelta(days=366)
    group_id = _parse_int_param(request.GET.get('group'))

    content = build_attendance_workbook(date_from, date_to, group_id=group_id)
    name = (
        f'attendance_{date_from}.xlsx' if date_from == date_to
        else f'attendance_{date_from}_to_{date_to}.xlsx'
    )
    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{name}"'
    return response


# ==================== Payment report ====================

@supervisor_required
def payment_report(request):
    """
    Comprehensive Payment Report with filters and statistics.

    A per-payment list (desk collection work) is supervisor-or-admin, but
    the cumulative totals (``total_due``/``total_paid``/``total_remaining``)
    are admin-only via ``show_financials`` — see the module docstring.
    """
    show_financials = request.user.can_see_financials()
    # Get filter parameters
    month = request.GET.get('month')
    status = request.GET.get('status')
    group_id = request.GET.get('group')
    teacher_id = request.GET.get('teacher')

    # Base queryset
    payments = _reportable_payments().select_related(
        'student', 'group', 'group__teacher'
    ).order_by('-month', '-payment_date')

    # Apply filters
    if month:
        month_start = parse_month_param(month)
        if month_start is None:
            # An unparseable ?month= used to produce a LIKE that matched
            # nothing; keep "no rows" rather than silently widening the report.
            payments = payments.none()
        else:
            payments = _month_filter(payments, month_start)
    if status:
        payments = payments.filter(status=status)
    if group_id:
        # A non-numeric id used to raise ValueError inside the ORM — a 500
        # (unvalidated-get-filters-500). Unparseable => no rows, matching
        # the ``?month=`` contract just above.
        group_id_parsed = _parse_int_param(group_id)
        payments = (
            payments.filter(group__group_id=group_id_parsed)
            if group_id_parsed is not None else payments.none()
        )
    if teacher_id:
        teacher_id_parsed = _parse_int_param(teacher_id)
        payments = (
            payments.filter(group__teacher__teacher_id=teacher_id_parsed)
            if teacher_id_parsed is not None else payments.none()
        )

    # ``?export=xlsx`` — every filtered row as a formatted workbook. Amounts
    # are per-payment desk data (the same the table shows), so no admin gate
    # beyond the page's own.
    if request.GET.get('export') == 'xlsx':
        from django.http import HttpResponse
        from .excel import build_payments_workbook
        parts = [f'الشهر {month}' if month else 'كل الشهور']
        content = build_payments_workbook(payments, subtitle=' · '.join(parts))
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = (
            f'attachment; filename="payments_{month or timezone.localdate()}.xlsx"'
        )
        return response

    # Statistics — one aggregate instead of five round-trips. The money sums
    # are only requested (and only ever reach the template) for an admin.
    agg_kwargs = {
        'paid': Count('payment_id', filter=Q(status='paid')),
        'partial': Count('payment_id', filter=Q(status='partial')),
        'unpaid': Count('payment_id', filter=Q(status='unpaid')),
    }
    if show_financials:
        agg_kwargs['total_due'] = Sum('amount_due')
        agg_kwargs['total_paid'] = Sum('amount_paid')
    stats = payments.aggregate(**agg_kwargs)
    total_due = stats.get('total_due') or 0
    total_paid = stats.get('total_paid') or 0

    # Group and teacher filter options
    groups = Group.objects.filter(is_active=True)
    teachers = Teacher.objects.filter(is_active=True)

    if request.GET.get('print'):
        from apps.core.templatetags.money_format import egp
        group_name = (
            groups.filter(group_id=_parse_int_param(group_id)).values_list('group_name', flat=True).first()
            if group_id else None
        )
        teacher_name = (
            teachers.filter(teacher_id=_parse_int_param(teacher_id)).values_list('full_name', flat=True).first()
            if teacher_id else None
        )
        status_label = dict(Payment.STATUS_CHOICES).get(status)
        rows = [
            [
                p.student.full_name, p.group.group_name if p.group else '',
                p.month.strftime('%Y-%m') if p.month else '',
                egp(p.amount_due), egp(p.amount_paid), egp(p.remaining),
                timezone.localtime(p.payment_date).strftime('%Y-%m-%d') if p.payment_date else '',
                p.get_status_display(),
            ]
            for p in payments[:PRINT_ROW_LIMIT]
        ]
        print_stats = [
            ('مدفوع بالكامل', stats['paid'] or 0),
            ('جزئي', stats['partial'] or 0),
            ('غير مدفوع', stats['unpaid'] or 0),
        ]
        if show_financials:
            print_stats += [
                ('إجمالي المستحق', egp(total_due)),
                ('إجمالي المحصل', egp(total_paid)),
                ('المتبقي', egp(total_due - total_paid)),
            ]
        return _render_list_print(
            request,
            title='سجل المدفوعات',
            filters=[
                f'الشهر: {month}' if month else 'كل الشهور',
                f'الحالة: {status_label}' if status_label else '',
                f'المجموعة: {group_name}' if group_name else '',
                f'المدرس: {teacher_name}' if teacher_name else '',
            ],
            stats=print_stats,
            columns=['الطالب', 'المجموعة', 'الشهر', 'المستحق', 'المدفوع', 'المتبقي', 'تاريخ الدفع', 'الحالة'],
            rows=rows,
            total=payments.count(),
        )

    # Pagination
    paginator = Paginator(payments, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'show_financials': show_financials,
        'paid_count': stats['paid'] or 0,
        'partial_count': stats['partial'] or 0,
        'unpaid_count': stats['unpaid'] or 0,
        'groups': groups,
        'teachers': teachers,
        'selected_month': month,
        'selected_status': status,
        'selected_group': group_id,
        'selected_teacher': teacher_id,
    }
    if show_financials:
        context.update({
            'total_due': total_due,
            'total_paid': total_paid,
            'total_remaining': total_due - total_paid,
        })

    return render(request, 'reports/payments.html', context)


def _cycle_cancelled(group, cycle):
    """الحصص الملغية في الدورة — مش محسوبة من حصصها."""
    return list(Session.objects.filter(group=group, is_cancelled=True).filter(
        Q(cycle=cycle) | Q(
            cycle__isnull=True, session_date__gte=cycle.started_on,
            **({'session_date__lte': cycle.closed_on} if cycle.closed_on else {}),
        )
    ).order_by('session_date'))


def _cycle_register_data(group, cycle):
    """Columns (one per lesson slot of ``cycle``) and one row per student:
    the cycle's payment date and, per lesson, the date attended / «غ» / «-»."""
    sessions = list(
        Session.objects.filter(cycle=cycle, sequence_in_cycle__isnull=False)
        .order_by('sequence_in_cycle')
    )
    slots = max(cycle.sessions_planned or 0, len(sessions))
    by_seq = {s.sequence_in_cycle: s for s in sessions}
    columns = [{'seq': i, 'session': by_seq.get(i)} for i in range(1, slots + 1)]

    attended = defaultdict(dict)
    for student_id, session_id, status in Attendance.objects.filter(
        session__in=sessions
    ).values_list('student_id', 'session_id', 'status'):
        attended[student_id][session_id] = status

    payments = {p.student_id: p for p in Payment.objects.filter(cycle=cycle).order_by('payment_id')}
    student_ids = set(payments) | set(attended) | set(
        StudentGroupEnrollment.objects.filter(group=group, is_active=True)
        .values_list('student_id', flat=True)
    )
    students = Student.objects.filter(pk__in=student_ids).order_by('full_name')

    today = timezone.localdate()
    rows = []
    for student in students:
        cells = []
        for col in columns:
            s = col['session']
            if s is None or (s.session_date > today and s.session_id not in attended[student.pk]):
                cells.append({'kind': 'future', 'text': '', 'session': s})
                continue
            status = attended[student.pk].get(s.session_id)
            if status in ('present', 'late', 'exception'):
                text = f'{s.session_date.month}/{s.session_date.day}'
            elif status == 'absent':
                text = 'غ'
            else:
                status, text = 'none', '-'
            cells.append({'kind': status, 'text': text, 'session': s})

        p = payments.get(student.pk)
        pay_date = None
        if p is not None:
            pay_date = p.paid_on or (timezone.localtime(p.payment_date).date() if p.payment_date else None)
        pay_status = 'exempt' if p and p.is_exempt else (p.status if p else 'unpaid')
        if pay_status == 'exempt':
            pay_text, note = 'معفى', ''
        elif pay_status in ('paid', 'partial'):
            pay_text = f'{pay_date.month}/{pay_date.day}' if pay_date else '✓'
            note = f'باقي {p.remaining:g}' if pay_status == 'partial' else ''
        else:
            pay_text, note = '', 'لم يدفع'
        rows.append({
            'student': student, 'payment': p, 'pay_status': pay_status,
            'pay_text': pay_text, 'note': note, 'cells': cells,
            'user_note': (p.notes or '') if p else '',
            'phone': student.parent_phone or student.student_phone,
        })
    return columns, rows


@supervisor_required
def cycle_register(request):
    """
    كشف المجموعة بالدورة — نفس شكل الكشف الورقي: صف لكل طالب، عمود دفع
    الدورة (تاريخ الدفع لهذه الدورة تحديدًا) ثم عمود لكل حصة من حصص الدورة
    فيه تاريخ حضور الطالب أو «غ» للغياب.
    """
    groups = Group.objects.filter(is_active=True).select_related('teacher').order_by('group_name')
    group = groups.filter(group_id=_parse_int_param(request.GET.get('group'))).first()
    context = {'groups': groups, 'group': group}
    if group is None:
        return render(request, 'reports/cycle_register.html', context)

    from apps.teachers.models import GroupCycle
    cycles = list(GroupCycle.objects.filter(group=group, started_on__isnull=False).order_by('-index'))
    cycle = None
    cycle_param = _parse_int_param(request.GET.get('cycle'))
    if cycle_param is not None:
        cycle = next((c for c in cycles if c.cycle_id == cycle_param), None)
    if cycle is None and cycles:
        cycle = next((c for c in cycles if c.is_open), cycles[0])
    context.update({'cycles': cycles, 'cycle': cycle})
    if cycle is None:
        return render(request, 'reports/cycle_register.html', context)

    if request.GET.get('export') == 'xlsx':
        from django.http import HttpResponse
        from .excel import build_cycle_register_workbook
        export_cycles = sorted(cycles, key=lambda c: c.index) if request.GET.get('all') else [cycle]
        for c in export_cycles:
            c._cancelled = _cycle_cancelled(group, c)
        content = build_cycle_register_workbook(
            group, [(c, *_cycle_register_data(group, c)) for c in export_cycles]
        )
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        suffix = 'all' if request.GET.get('all') else f'cycle{cycle.index}'
        response['Content-Disposition'] = f'attachment; filename="register_{group.group_id}_{suffix}.xlsx"'
        return response

    # الدورات فوق بعض بالترتيب — أول ما الدورة تخلص 8 حصص والجديدة تتفتح،
    # بتظهر تحتها لوحدها. ``?cycle=`` يعرض دورة واحدة بس.
    shown = [cycle] if request.GET.get('only') else sorted(cycles, key=lambda c: c.index)
    sheets = []
    for c in shown:
        columns, rows = _cycle_register_data(group, c)
        cancelled = _cycle_cancelled(group, c)
        sheets.append({
            'cycle': c,
            'columns': columns,
            'rows': rows,
            'cancelled': cancelled,
            'blank_rows': range(max(2, 17 - len(rows))),
            'paid_count': sum(1 for r in rows if r['pay_status'] in ('paid', 'exempt')),
            'unpaid_count': sum(1 for r in rows if r['pay_status'] not in ('paid', 'exempt')),
        })
    context['sheets'] = sheets
    return render(request, 'reports/cycle_register.html', context)


@ajax_supervisor_required
def cycle_register_note(request):
    """حفظ ملاحظة من كشف الدورة: ملاحظة طالب (على دفعته في الدورة) أو ملاحظة
    المجموعة على الدورة نفسها."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST فقط'}, status=405)
    from apps.teachers.models import GroupCycle
    text = (request.POST.get('text') or '').strip()[:1000]
    kind = request.POST.get('kind')
    if kind == 'student':
        obj = Payment.objects.filter(pk=_parse_int_param(request.POST.get('id'))).select_related('student', 'cycle').first()
        if obj is None:
            return JsonResponse({'success': False, 'error': 'الدفعة غير موجودة'}, status=404)
        obj.notes = text
        obj.save(update_fields=['notes'])
        label = f'ملاحظة الطالب {obj.student.full_name} — دورة {obj.cycle.index if obj.cycle else ""}'
        model = 'Payment'
    elif kind == 'cycle':
        obj = GroupCycle.objects.filter(pk=_parse_int_param(request.POST.get('id'))).select_related('group').first()
        if obj is None:
            return JsonResponse({'success': False, 'error': 'الدورة غير موجودة'}, status=404)
        obj.notes = text
        obj.save(update_fields=['notes'])
        label = f'ملاحظة المجموعة {obj.group.group_name} — دورة {obj.index}'
        model = 'GroupCycle'
    else:
        return JsonResponse({'success': False, 'error': 'نوع غير معروف'}, status=400)
    ActivityLog.log(
        user=request.user, action='group_update',
        description=f'{label}: {text or "(اتمسحت)"}',
        target_model=model, target_id=obj.pk, request=request,
    )
    return JsonResponse({'success': True})


# ==================== Financial report ====================

@admin_required
def financial_report(request):
    """
    Detailed Financial Report — centre revenue and teacher settlements.

    Admin only (AUTH-09): this is the whole centre's money, not desk work.
    """
    this_month = timezone.localdate().replace(day=1)

    # Twelve real calendar months. Subtracting ``i * 30`` days skipped and
    # repeated months (PERF-07).
    months = [add_months(this_month, -i) for i in range(11, -1, -1)]
    range_start = months[0]
    range_end = add_months(months[-1], 1)

    # One grouped query for all twelve months instead of 4 aggregates × 12.
    monthly_rows = {
        row['bucket']: row
        for row in (
            _reportable_payments()
            .filter(month__gte=range_start, month__lt=range_end)
            .annotate(bucket=TruncMonth('month'))
            .values('bucket')
            .annotate(
                total_due=Sum('amount_due'),
                total_paid=Sum('amount_paid'),
                paid_count=Count('payment_id', filter=Q(status='paid')),
                unpaid_count=Count('payment_id', filter=Q(status='unpaid')),
            )
            .order_by()
        )
    }

    monthly_data = []
    for month_date in months:
        row = monthly_rows.get(month_date) or {}
        monthly_data.append({
            # ``date`` filter, not strftime: the site locale gives Arabic month names.
            'month_name': date_filter(month_date, 'F Y'),
            'total_due': row.get('total_due') or 0,
            'total_paid': row.get('total_paid') or 0,
            'paid_count': row.get('paid_count') or 0,
            'unpaid_count': row.get('unpaid_count') or 0,
        })

    # ---- Teacher settlements summary (3 queries, not 2 per teacher) ----
    teachers = list(Teacher.objects.filter(is_active=True))
    teacher_ids = [t.pk for t in teachers]

    group_counts = dict(
        Group.objects.filter(teacher_id__in=teacher_ids, is_active=True)
        .values_list('teacher_id')
        .annotate(n=Count('group_id'))
        .order_by()
        .values_list('teacher_id', 'n')
    )
    # Revenue is summed over ALL of the teacher's groups, active or not: a
    # group deactivated mid-month still earned the money it collected, and
    # filtering on ``is_active=True`` made that revenue disappear (DATA-23).
    # Same reasoning for the teacher: one who was deactivated or sent to the
    # recycle bin still collected that money, so they stay in the table
    # (flagged) instead of their revenue silently dropping out of the total.
    revenue = dict(
        Payment.objects.filter(group__teacher__isnull=False, amount_paid__gt=0)
        .values_list('group__teacher_id')
        .annotate(total=Sum('amount_paid'))
        .order_by()
        .values_list('group__teacher_id', 'total')
    )
    teachers += list(Teacher.all_objects.filter(pk__in=set(revenue) - set(teacher_ids)))

    teacher_stats = [
        {
            'name': teacher.full_name,
            'groups_count': group_counts.get(teacher.pk, 0),
            'total_revenue': revenue.get(teacher.pk) or 0,
            'is_active': teacher.is_active and teacher.deleted_at is None,
            'is_deleted': teacher.deleted_at is not None,
        }
        for teacher in teachers
    ]

    context = {
        'monthly_data': json.dumps(monthly_data, ensure_ascii=False, default=str),
        'teacher_stats': teacher_stats,
    }

    return render(request, 'reports/financial.html', context)


# ==================== Activity Log ====================

@admin_required
def activity_log(request):
    """
    سجل النشاط - عرض جميع العمليات التي قام بها المستخدمون

    Admin only (AUTH-10): the log holds usernames and client IP addresses.
    """
    from apps.accounts.models import User

    logs = ActivityLog.objects.select_related('user').order_by('-created_at')

    # Filters
    action_filter = request.GET.get('action', '')
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if action_filter:
        logs = logs.filter(action=action_filter)
    if user_filter:
        # A non-numeric id used to raise ValueError inside the ORM — a 500
        # (unvalidated-get-filters-500). Unparseable => no rows.
        user_id_parsed = _parse_int_param(user_filter)
        logs = (
            logs.filter(user_id=user_id_parsed)
            if user_id_parsed is not None else logs.none()
        )
    if date_from:
        date_from_parsed = _parse_date_param(date_from)
        logs = (
            logs.filter(created_at__date__gte=date_from_parsed)
            if date_from_parsed else logs.none()
        )
    if date_to:
        date_to_parsed = _parse_date_param(date_to)
        logs = (
            logs.filter(created_at__date__lte=date_to_parsed)
            if date_to_parsed else logs.none()
        )

    # Pagination
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs_page = paginator.get_page(page)

    context = {
        'logs': logs_page,
        'action_choices': ActivityLog.ACTION_CHOICES,
        'users': User.objects.filter(is_active=True).order_by('username'),
        'current_action': action_filter,
        'current_user': user_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'reports/activity_log.html', context)


# ==================== Recycle Bin ====================

RECYCLE_MODELS = {
    'student': Student,
    'teacher': Teacher,
    'group': Group,
    'room': Room,
}


def _bin_section(queryset, visible):
    """Return ``(items_for_template, count)`` without counting twice."""
    if visible:
        items = list(queryset)
        return items, len(items)
    return [], queryset.count()


@supervisor_required
def recycle_bin(request):
    """
    سلة المهملات - عرض العناصر المحذوفة مع إمكانية الاستعادة أو الحذف النهائي

    Supervisor or admin (AUTH-11). Permanent deletion stays admin-only.
    """
    filter_type = request.GET.get('type', 'all')

    students, students_count = _bin_section(
        Student.all_objects.dead().select_related('deleted_by'),
        filter_type in ('all', 'students'),
    )
    teachers, teachers_count = _bin_section(
        Teacher.all_objects.dead().select_related('deleted_by'),
        filter_type in ('all', 'teachers'),
    )
    groups, groups_count = _bin_section(
        # recycle_bin.html reads group.teacher.full_name in the loop for
        # every deleted group (Group.teacher is non-nullable), which cost one
        # extra SELECT per row without this (recycle-bin-unbounded-and-n1).
        Group.all_objects.dead().select_related('deleted_by', 'teacher'),
        filter_type in ('all', 'groups'),
    )
    rooms, rooms_count = _bin_section(
        Room.all_objects.dead().select_related('deleted_by'),
        filter_type in ('all', 'rooms'),
    )

    context = {
        'deleted_students': students,
        'deleted_teachers': teachers,
        'deleted_groups': groups,
        'deleted_rooms': rooms,
        'students_count': students_count,
        'teachers_count': teachers_count,
        'groups_count': groups_count,
        'rooms_count': rooms_count,
        'total_count': students_count + teachers_count + groups_count + rooms_count,
        'current_type': filter_type,
        'is_admin': request.user.role == 'admin',
        'empty_confirm_word': RECYCLE_EMPTY_CONFIRM,
    }

    return render(request, 'reports/recycle_bin.html', context)


@ajax_supervisor_required
def recycle_restore(request):
    """استعادة عنصر من سلة المهملات"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    item_type = request.POST.get('type')
    item_id = request.POST.get('id')

    if not item_type or not item_id:
        return JsonResponse({'success': False, 'message': 'بيانات ناقصة'})

    model = RECYCLE_MODELS.get(item_type)
    if not model:
        return JsonResponse({'success': False, 'message': 'نوع غير صالح'})

    try:
        obj = model.all_objects.get(pk=item_id)
        obj.restore()

        ActivityLog.log(
            user=request.user,
            # 'update' was not a valid ACTION_CHOICES value, so the log line
            # rendered raw and the filter dropdown could not select it
            # (DATA-24).
            action='restore',
            description=f'استعادة {item_type} من سلة المهملات: {obj}',
            target_model=item_type.capitalize(),
            target_id=item_id,
            request=request
        )

        return JsonResponse({
            'success': True,
            'message': 'تم استعادة العنصر بنجاح'
        })
    except (model.DoesNotExist, ValueError, TypeError):
        # A non-numeric id (hand-crafted request; the template only ever
        # emits integer pks) makes ``pk=item_id`` raise ValueError instead of
        # DoesNotExist, which used to escape as an uncaught 500 with an HTML
        # body that broke the caller's ``r.json()`` (recycle-ajax-bad-id-500).
        return JsonResponse({'success': False, 'message': 'العنصر غير موجود'})


@ajax_admin_required
def recycle_permanent_delete(request):
    """حذف نهائي من سلة المهملات - للمدير فقط"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    item_type = request.POST.get('type')
    item_id = request.POST.get('id')

    if not item_type or not item_id:
        return JsonResponse({'success': False, 'message': 'بيانات ناقصة'})

    model = RECYCLE_MODELS.get(item_type)
    if not model:
        return JsonResponse({'success': False, 'message': 'نوع غير صالح'})

    try:
        obj = model.all_objects.get(pk=item_id)
        if not obj.is_deleted:
            return JsonResponse({'success': False, 'message': 'لا يمكن حذف عنصر غير موجود في سلة المهملات'})

        obj_name = str(obj)
        from apps.core.purge import PURGERS, PurgeRefused, records_summary
        if item_type in PURGERS:
            summary = records_summary(item_type, obj)
            has_records = summary['payments'] or summary['attendance']
            if has_records and request.POST.get('with_records') != '1':
                # The client asks again, naming what goes with it, then
                # retries with ``with_records=1`` — a real delete, records too.
                return JsonResponse({
                    'success': False, 'code': 'has_records', **summary,
                    'message': f'مرتبط بـ {summary["payments"]} دفعة و {summary["attendance"]} سجل حضور',
                })
            try:
                PURGERS[item_type](obj)
            except PurgeRefused as exc:
                return JsonResponse({'success': False, 'message': str(exc)})
            if has_records:
                obj_name += f' (مع {summary["payments"]} دفعة و {summary["attendance"]} سجل حضور)'
        else:
            model.all_objects.filter(pk=item_id).hard_delete()

        ActivityLog.log(
            user=request.user,
            action='permanent_delete',
            description=f'حذف نهائي {item_type}: {obj_name}',
            target_model=item_type.capitalize(),
            target_id=item_id,
            request=request
        )

        return JsonResponse({
            'success': True,
            'message': 'تم الحذف النهائي بنجاح'
        })
    except (model.DoesNotExist, ValueError, TypeError):
        # A non-numeric id (hand-crafted request; the template only ever
        # emits integer pks) makes ``pk=item_id`` raise ValueError instead of
        # DoesNotExist, which used to escape as an uncaught 500 with an HTML
        # body that broke the caller's ``r.json()`` (recycle-ajax-bad-id-500).
        return JsonResponse({'success': False, 'message': 'العنصر غير موجود'})
    except ProtectedError:
        return JsonResponse({'success': False, 'message': 'لا يمكن حذف هذا العنصر لأنه مرتبط بسجلات أخرى (مدفوعات أو حضور). يرجى حذف السجلات المرتبطة أولاً.'})


def _ids_with_financial_history(dead_students):
    """Student ids that must never be purged: they have money or attendance."""
    blocked = set(
        Payment.objects.filter(student__in=dead_students)
        .values_list('student_id', flat=True)
    )
    blocked |= set(
        Attendance.objects.filter(student__in=dead_students)
        .values_list('student_id', flat=True)
    )
    return blocked


def _group_ids_with_financial_history(dead_groups):
    """Group ids that must never be purged: they have money or attendance."""
    blocked = set(
        Payment.objects.filter(group__in=dead_groups)
        .values_list('group_id', flat=True)
    )
    blocked |= set(
        Attendance.objects.filter(session__group__in=dead_groups)
        .values_list('session__group_id', flat=True)
    )
    return blocked


@admin_required
def recycle_empty(request):
    """
    تفريغ سلة المهملات - للمدير فقط.

    This used to cascade-delete ``Attendance`` **and ``Payment``** rows for
    every soft-deleted student and group before hard-deleting them: one POST
    permanently destroyed the centre's accounting history, irreversibly, with
    no export and no per-item confirmation (DATA-25).

    It is now conservative:

    * the admin must type the confirmation word (``RECYCLE_EMPTY_CONFIRM``)
      into the form — a JS ``confirm()`` dialog is not consent for this;
    * any student or group that still has a ``Payment`` or ``Attendance`` row
      is **skipped**, never purged. Financial and attendance history is only
      removable by someone who deliberately removes those records first;
    * everything actually removed is written to the activity log, itemised.
    """
    if request.method != 'POST':
        messages.error(request, 'طريقة غير مسموح بها.')
        return redirect('reports:recycle_bin')

    if request.POST.get('confirm', '').strip() != RECYCLE_EMPTY_CONFIRM:
        messages.error(
            request,
            f'لتأكيد تفريغ سلة المهملات اكتب كلمة «{RECYCLE_EMPTY_CONFIRM}» في خانة التأكيد.'
        )
        return redirect('reports:recycle_bin')

    removed = {'students': 0, 'groups': 0, 'teachers': 0, 'rooms': 0}
    kept = {'students': 0, 'groups': 0, 'teachers': 0, 'rooms': 0}
    removed_names = []

    try:
        with transaction.atomic():
            # ── 1) الطلاب المحذوفون بدون سجلات مالية أو حضور ──────────────
            dead_students = Student.all_objects.dead()
            blocked_students = _ids_with_financial_history(dead_students)
            purgeable = list(
                dead_students.exclude(pk__in=blocked_students)
                .values_list('pk', 'full_name')
            )
            kept['students'] = len(blocked_students)
            if purgeable:
                ids = [pk for pk, _ in purgeable]
                StudentGroupEnrollment.objects.filter(student_id__in=ids).delete()
                Student.all_objects.filter(pk__in=ids).hard_delete()
                removed['students'] = len(ids)
                removed_names.extend(f'طالب: {name}' for _, name in purgeable)

            # ── 2) المجموعات المحذوفة بدون سجلات مالية أو حضور ────────────
            dead_groups = Group.all_objects.dead()
            blocked_groups = _group_ids_with_financial_history(dead_groups)
            purgeable_groups = list(
                dead_groups.exclude(pk__in=blocked_groups)
                .values_list('pk', 'group_name')
            )
            kept['groups'] = len(blocked_groups)
            if purgeable_groups:
                ids = [pk for pk, _ in purgeable_groups]
                Session.objects.filter(group_id__in=ids).delete()
                StudentGroupEnrollment.objects.filter(group_id__in=ids).delete()
                Group.all_objects.filter(pk__in=ids).hard_delete()
                removed['groups'] = len(ids)
                removed_names.extend(f'مجموعة: {name}' for _, name in purgeable_groups)

            # ── 3) المدرسون والقاعات المحذوفون بدون مجموعات مرتبطة ────────
            dead_teachers = Teacher.all_objects.dead()
            busy_teachers = set(
                Group.all_objects.filter(teacher__in=dead_teachers)
                .values_list('teacher_id', flat=True)
            )
            purgeable_teachers = list(
                dead_teachers.exclude(pk__in=busy_teachers)
                .values_list('pk', 'full_name')
            )
            kept['teachers'] = len(busy_teachers)
            if purgeable_teachers:
                ids = [pk for pk, _ in purgeable_teachers]
                Teacher.all_objects.filter(pk__in=ids).hard_delete()
                removed['teachers'] = len(ids)
                removed_names.extend(f'مدرس: {name}' for _, name in purgeable_teachers)

            dead_rooms = Room.all_objects.dead()
            busy_rooms = set(
                Group.all_objects.filter(room__in=dead_rooms)
                .values_list('room_id', flat=True)
            )
            purgeable_rooms = list(
                dead_rooms.exclude(pk__in=busy_rooms).values_list('pk', 'name')
            )
            kept['rooms'] = len(busy_rooms)
            if purgeable_rooms:
                ids = [pk for pk, _ in purgeable_rooms]
                Room.all_objects.filter(pk__in=ids).hard_delete()
                removed['rooms'] = len(ids)
                removed_names.extend(f'قاعة: {name}' for _, name in purgeable_rooms)

    except ProtectedError as exc:
        protected_names = ', '.join(str(obj) for obj in list(exc.protected_objects)[:3])
        messages.error(
            request,
            f'لا يمكن الحذف: بعض العناصر مرتبطة بسجلات أخرى ({protected_names}...)'
        )
        return redirect('reports:recycle_bin')
    except Exception:
        # QUAL-01: never echo the raw exception text to the browser — it leaks
        # model names, SQL fragments and file paths. It goes to the log.
        logger.exception('recycle_empty failed for user %s', request.user.pk)
        messages.error(request, 'حدث خطأ أثناء تفريغ سلة المهملات. تمت مراجعة السجل.')
        return redirect('reports:recycle_bin')

    total_removed = sum(removed.values())
    total_kept = sum(kept.values())

    ActivityLog.log(
        user=request.user,
        action='permanent_delete',
        description=(
            f'تفريغ سلة المهملات: حُذف نهائياً {total_removed} عنصر '
            f'(طلاب: {removed["students"]}، مجموعات: {removed["groups"]}، '
            f'مدرسون: {removed["teachers"]}، قاعات: {removed["rooms"]}). '
            f'تم تخطي {total_kept} عنصر لارتباطه بسجلات مالية أو حضور. '
            + ('العناصر المحذوفة: ' + ' | '.join(removed_names[:50]) if removed_names else '')
        ),
        target_model='RecycleBin',
        target_id=0,
        request=request
    )

    if total_removed:
        messages.success(request, f'تم تفريغ سلة المهملات ({total_removed} عنصر)')
    else:
        messages.info(request, 'لا يوجد عنصر يمكن حذفه نهائياً من سلة المهملات.')
    if total_kept:
        messages.warning(
            request,
            f'تم الاحتفاظ بـ {total_kept} عنصر لأنه مرتبط بسجلات مالية أو سجلات حضور. '
            'لا يتم حذف السجلات المالية تلقائياً.'
        )
    return redirect('reports:recycle_bin')


# ==================== Tsfya — monthly financial summary ====================

@admin_required
def monthly_financial_summary(request):
    """
    Tsfya (تصفية) — Monthly Financial Summary dashboard.

    Shows a month-by-month breakdown per student per group:
    - Who has paid
    - Who hasn't paid
    - Remaining balances
    - Collection rates
    - Payment status distribution

    Every figure here is a cumulative, centre-wide total — admin only.
    It used to be supervisor-or-admin (AUTH-09); nothing on this page is
    desk-collection work (that's ``payment_report``), so there is nothing
    for a supervisor to legitimately need here.
    """
    # Determine month
    report_month = parse_month_param(request.GET.get('month')) or \
        timezone.localdate().replace(day=1)

    # All payments for the selected month
    payments_qs = _reportable_payments().filter(month=report_month).select_related(
        'student', 'group', 'group__teacher'
    ).order_by('status', '-amount_due')

    # --- Summary statistics ---
    total_students = payments_qs.values('student').distinct().count()
    totals = payments_qs.aggregate(
        paid=Count('payment_id', filter=Q(status='paid')),
        partial=Count('payment_id', filter=Q(status='partial')),
        unpaid=Count('payment_id', filter=Q(status='unpaid')),
        total_due=Sum('amount_due'),
        total_paid=Sum('amount_paid'),
    )
    total_due = totals['total_due'] or 0
    total_paid = totals['total_paid'] or 0

    # --- Per-group breakdown ---
    # One GROUP BY query for every group instead of 7 queries per group
    # (PERF-06). ``.order_by()`` is essential: the base queryset is ordered by
    # status/amount, and those columns would otherwise join the GROUP BY.
    rows = {
        row['group_id']: row
        for row in (
            payments_qs
            .values('group_id')
            .annotate(
                total_students=Count('payment_id'),
                paid=Count('payment_id', filter=Q(status='paid')),
                partial=Count('payment_id', filter=Q(status='partial')),
                unpaid=Count('payment_id', filter=Q(status='unpaid')),
                due=Sum('amount_due'),
                paid_amount=Sum('amount_paid'),
            )
            .order_by()
        )
    }

    # ``rows`` is keyed by every group_id the month's payments touch, whether
    # or not the group is still active. Resolving through the default
    # ``is_active=True`` manager silently dropped deactivated/soft-deleted
    # groups from this breakdown while the header tiles above (built from
    # ``payments_qs`` directly) still counted their payments — the per-group
    # column totals fell short of the header by exactly that group's money
    # (tsfya-breakdown-drops-inactive-groups). ``all_objects`` includes
    # soft-deleted groups too; the payment rows already scope the report.
    groups = Group.all_objects.filter(
        group_id__in=list(rows.keys())
    ).select_related('teacher').order_by('group_name')

    group_breakdown = []
    for group in groups:
        row = rows[group.group_id]
        g_due = row['due'] or 0
        g_paid_amt = row['paid_amount'] or 0
        group_breakdown.append({
            'group_id': group.group_id,
            'group_name': group.group_name,
            'teacher_name': group.teacher.full_name if group.teacher else '—',
            'total_students': row['total_students'],
            'paid': row['paid'],
            'partial': row['partial'],
            'unpaid': row['unpaid'],
            'due': g_due,
            'paid_amount': g_paid_amt,
            'remaining': g_due - g_paid_amt,
            'collection_rate': round(_rate(g_paid_amt, g_due), 1),
        })

    # --- Drill-down: every figure on the page links here ---
    # Client: "لما يشوف التحصيل 59%، عايز لما يدوس عليها تفتحله مين اللي دفعوا
    # ومين اللي ما دفعش. كل رقم في التقرير عايزه clickable". The figures
    # link back to this page with ``status``/``group``; the records table
    # below is filtered to exactly the rows behind the figure clicked.
    records_qs, drill = _drill_payments(payments_qs, {} if feature_lock.is_locked() else request.GET)
    if drill['status'] == 'split':
        split_paid = list(records_qs.filter(status__in=['paid', 'partial']).order_by('group__group_name', 'student__full_name'))
        split_unpaid = list(records_qs.filter(status='unpaid').order_by('group__group_name', 'student__full_name'))
    else:
        split_paid = split_unpaid = None

    # --- Payment records (paginated) ---
    paginator = Paginator(records_qs, 30)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # --- Available months for navigation ---
    distinct_months = Payment.objects.dates('month', 'month', order='DESC')[:12]

    context = {
        'page_title': 'التصفية الشهرية — Tsfya',
        'report_month': report_month,
        'distinct_months': distinct_months,
        'total_students': total_students,
        'paid_count': totals['paid'] or 0,
        'partial_count': totals['partial'] or 0,
        'unpaid_count': totals['unpaid'] or 0,
        'total_due': total_due,
        'total_paid': total_paid,
        'total_remaining': total_due - total_paid,
        'collection_rate': round(_rate(total_paid, total_due), 1),
        'group_breakdown': group_breakdown,
        'page_obj': page_obj,
        'drill': drill,
        'split_paid': split_paid,
        'split_unpaid': split_unpaid,
        'monthly_data_json': json.dumps(group_breakdown, ensure_ascii=False, default=str),
    }

    return render(request, 'reports/tsfya.html', context)


#: What each drill-down ``status`` means, and how the records table says it.
DRILL_STATUSES = {
    'paid': ('مدفوع بالكامل', Q(status='paid')),
    'partial': ('مدفوع جزئياً', Q(status='partial')),
    'unpaid': ('غير مدفوع', Q(status='unpaid')),
    'owing': ('عليهم مبالغ متبقية', Q(status__in=['unpaid', 'partial'])),
    'collected': ('دفعوا (كامل أو جزئي)', Q(amount_paid__gt=0)),
    'split': ('مين دفع ومين ما دفعش', Q()),
}


def _drill_payments(payments_qs, params):
    """
    Narrow a report's payments to the rows behind one clicked figure.

    ``status`` is a key of :data:`DRILL_STATUSES`; ``group`` a group id.
    Returns ``(queryset, drill)`` where ``drill`` describes the active filter
    for the page (label, group, and whether any filter is on).
    """
    status = params.get('status') or ''
    if status not in DRILL_STATUSES:
        status = ''
    group = None
    group_id = params.get('group')
    if group_id and str(group_id).isdigit():
        group = Group.all_objects.filter(pk=int(group_id)).select_related('teacher').first()

    qs = payments_qs
    if status:
        qs = qs.filter(DRILL_STATUSES[status][1])
    if group is not None:
        qs = qs.filter(group=group)
    return qs, {
        'status': status,
        'label': DRILL_STATUSES[status][0] if status else '',
        'group': group,
        'active': bool(status or group),
    }


# ==================== Comprehensive (cumulative) report ====================

@admin_required
def comprehensive_report(request):
    """
    التقرير الشامل التراكمي — من أول طالب مسجَّل حتى اليوم افتراضيًا، مع
    إمكانية تضييق المدى لأي فترة، وفلترة بالمجموعة أو المدرس.

    يغطي طلب العميل: «سجل تراكمي ومنظم من أول يوم عمل أو أول طالب تم تسجيله
    وحتى تاريخ اليوم، مع إمكانية استخراج تقارير شاملة لأي مجموعة أو فترة».
    التقارير الأخرى كلها مُقيَّدة بشهر واحد (``payments``/``tsfya``) أو
    بآخر 12 شهرًا (``financial``)؛ هذه هي الوحيدة بمدى حر.

    ``?export=csv`` يُرجع نفس البيانات كملف CSV بترميز UTF-8 مع BOM حتى
    يفتحه إكسل بالعربي بشكل صحيح (نفس علاج FE-06 في تصدير الحضور).

    مالية تراكمية على مستوى السنتر ⇒ للأدمن فقط.
    """
    import csv

    from django.http import HttpResponse

    today = timezone.localdate()

    # ── المدى الافتراضي: من أول طالب مسجَّل (أو أول دفعة) حتى اليوم ──
    earliest_student = Student.all_objects.order_by('created_at').values_list(
        'created_at', flat=True
    ).first()
    earliest_payment = Payment.objects.order_by('month').values_list('month', flat=True).first()

    candidates = []
    if earliest_student:
        candidates.append(timezone.localtime(earliest_student).date())
    if earliest_payment:
        candidates.append(earliest_payment)
    default_from = min(candidates) if candidates else today.replace(day=1)

    date_from = _parse_date_param(request.GET.get('date_from')) or default_from
    date_to = _parse_date_param(request.GET.get('date_to')) or today
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    group_id = _parse_int_param(request.GET.get('group'))
    teacher_id = _parse_int_param(request.GET.get('teacher'))

    # ── المدفوعات في المدى ──
    # ``month`` هو أول يوم في شهر الفوترة، فالمدى يُقارن على مستوى الشهر
    # حتى لا يسقط شهر بدأ قبل ``date_from`` بأيام.
    payments = _reportable_payments().filter(
        month__gte=date_from.replace(day=1), month__lte=date_to,
    ).select_related('student', 'group', 'group__teacher')
    if group_id is not None:
        payments = payments.filter(group__group_id=group_id)
    if teacher_id is not None:
        payments = payments.filter(group__teacher__teacher_id=teacher_id)

    totals = payments.aggregate(
        total_due=Sum('amount_due'),
        total_paid=Sum('amount_paid'),
        rows=Count('payment_id'),
        students=Count('student_id', distinct=True),
    )
    total_due = totals['total_due'] or 0
    total_paid = totals['total_paid'] or 0

    # ── الحضور في المدى ──
    attendances = Attendance.objects.filter(
        session__session_date__gte=date_from, session__session_date__lte=date_to,
        session__is_cancelled=False,
    )
    if group_id is not None:
        attendances = attendances.filter(session__group__group_id=group_id)
    if teacher_id is not None:
        attendances = attendances.filter(session__group__teacher__teacher_id=teacher_id)

    att_totals = attendances.aggregate(
        present=Count('attendance_id', filter=Q(status='present')),
        late=Count('attendance_id', filter=Q(status='late')),
        absent=Count('attendance_id', filter=Q(status='absent')),
        exception=Count('attendance_id', filter=Q(status='exception')),
    )
    attended = (att_totals['present'] or 0) + (att_totals['late'] or 0)
    att_total = attended + (att_totals['absent'] or 0) + (att_totals['exception'] or 0)

    sessions_qs = Session.objects.filter(
        session_date__gte=date_from, session_date__lte=date_to, is_cancelled=False,
    )
    if group_id is not None:
        sessions_qs = sessions_qs.filter(group__group_id=group_id)
    if teacher_id is not None:
        sessions_qs = sessions_qs.filter(group__teacher__teacher_id=teacher_id)
    sessions_count = sessions_qs.count()

    # ── التفصيل لكل مجموعة: استعلام GROUP BY واحد لكل بُعد، لا حلقة فيها استعلامات ──
    # ``.order_by()`` إلزامي: ترتيب Meta الافتراضي كان سينضم إلى GROUP BY
    # ويُرجع صفًا لكل دفعة بدل صف لكل مجموعة (نفس فخ PERF-06).
    money_rows = {
        row['group_id']: row
        for row in payments.values('group_id').annotate(
            due=Sum('amount_due'), paid=Sum('amount_paid'),
            students=Count('student_id', distinct=True),
        ).order_by()
    }
    att_rows = {
        row['session__group_id']: row
        for row in attendances.values('session__group_id').annotate(
            present=Count('attendance_id', filter=Q(status='present')),
            late=Count('attendance_id', filter=Q(status='late')),
            absent=Count('attendance_id', filter=Q(status='absent')),
        ).order_by()
    }

    # ``all_objects`` يشمل المجموعات المحذوفة/المعطّلة — مجموعة أُغلقت في
    # منتصف المدى ما زالت حقّقت إيرادًا فيه، واستبعادها يجعل مجموع الصفوف
    # أقل من الإجمالي في الأعلى (نفس علة tsfya-breakdown-drops-inactive-groups).
    breakdown_ids = set(money_rows) | set(att_rows)
    groups_by_id = {
        g.group_id: g
        for g in Group.all_objects.filter(group_id__in=breakdown_ids).select_related('teacher')
    }

    breakdown = []
    for gid in breakdown_ids:
        group = groups_by_id.get(gid)
        m = money_rows.get(gid, {})
        a = att_rows.get(gid, {})
        g_due = m.get('due') or 0
        g_paid = m.get('paid') or 0
        g_present = (a.get('present') or 0) + (a.get('late') or 0)
        g_absent = a.get('absent') or 0
        breakdown.append({
            'group_id': gid,
            'group_name': group.group_name if group else f'#{gid}',
            'teacher_name': group.teacher.full_name if (group and group.teacher) else '—',
            'is_active': bool(group and group.is_active and group.deleted_at is None),
            'students': m.get('students') or 0,
            'due': g_due,
            'paid': g_paid,
            'remaining': g_due - g_paid,
            'collection_rate': round(_rate(g_paid, g_due), 1),
            'present': g_present,
            'absent': g_absent,
            'attendance_rate': round(_rate(g_present, g_present + g_absent), 1),
        })
    breakdown.sort(key=lambda r: r['group_name'])

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = (
            f'attachment; filename="comprehensive_{date_from}_{date_to}.csv"'
        )
        response.write('﻿')  # BOM — بدونه إكسل يعرض العربي مشفّرًا
        writer = csv.writer(response)
        writer.writerow(['التقرير الشامل', f'من {date_from}', f'إلى {date_to}'])
        writer.writerow([])
        writer.writerow([
            'المجموعة', 'المدرس', 'الحالة', 'عدد الطلاب', 'المستحق', 'المحصل',
            'المتبقي', 'نسبة التحصيل %', 'حضور', 'غياب', 'نسبة الحضور %',
        ])
        for row in breakdown:
            writer.writerow([
                row['group_name'], row['teacher_name'],
                'نشطة' if row['is_active'] else 'مغلقة',
                row['students'], row['due'], row['paid'], row['remaining'],
                row['collection_rate'], row['present'], row['absent'],
                row['attendance_rate'],
            ])
        writer.writerow([])
        writer.writerow([
            'الإجمالي', '', '', totals['students'] or 0, total_due, total_paid,
            total_due - total_paid, round(_rate(total_paid, total_due), 1),
            attended, att_totals['absent'] or 0,
            round(_rate(attended, att_total), 1),
        ])
        return response

    # ── Drill-down: the rows behind any figure ──
    # Client: "عايز يدوس على اي رقم (المستحق، المحصل، المتبقي، حضور، غياب)
    # ويعرف التفاصيل: مين دفع، مين حضر، مين غاب، المجموعة فيها مين".
    from urllib.parse import urlencode as _urlencode
    range_params = {'date_from': date_from.isoformat(), 'date_to': date_to.isoformat()}
    if teacher_id is not None:
        range_params['teacher'] = teacher_id
    base_params = dict(range_params)
    if group_id is not None:
        base_params['group'] = group_id
    # تفاصيل الأرقام ميزة من التحديث الأخير — مقفولة لحد السداد (config/feature_lock.py).
    detail_kind = '' if feature_lock.is_locked() else (request.GET.get('detail') or '')
    detail_title, detail_page, detail_type = '', None, ''
    payment_kinds = {
        'due': ('كل المستحقات', Q()),
        'paid': ('مين دفع', Q(amount_paid__gt=0)),
        'remaining': ('مين عليه متبقي', Q(status__in=['unpaid', 'partial'])),
        'unpaid': ('مين ما دفعش خالص', Q(status='unpaid')),
    }
    attendance_kinds = {
        'attended': ('مين حضر', Q(status__in=['present', 'late'])),
        'present': ('حضور في الميعاد', Q(status='present')),
        'late': ('مين اتأخر', Q(status='late')),
        'absent': ('مين غاب', Q(status='absent')),
    }
    if detail_kind in payment_kinds:
        detail_title, cond = payment_kinds[detail_kind]
        detail_type = 'payments'
        rows = payments.filter(cond).select_related('cycle').order_by('group__group_name', 'student__full_name')
        detail_page = Paginator(rows, 50).get_page(request.GET.get('dpage'))
    elif detail_kind in attendance_kinds:
        detail_title, cond = attendance_kinds[detail_kind]
        detail_type = 'attendance'
        rows = (
            attendances.filter(cond)
            .select_related('student', 'session', 'session__group')
            .order_by('-session__session_date', 'session__group__group_name', 'student__full_name')
        )
        detail_page = Paginator(rows, 50).get_page(request.GET.get('dpage'))
    elif detail_kind == 'members':
        from apps.students.models import StudentGroupEnrollment
        detail_title, detail_type = 'الطلاب المشتركين', 'members'
        rows = StudentGroupEnrollment.objects.filter(
            is_active=True, student__deleted_at__isnull=True,
        ).select_related('student', 'group', 'group__teacher')
        if group_id is not None:
            rows = rows.filter(group__group_id=group_id)
        if teacher_id is not None:
            rows = rows.filter(group__teacher__teacher_id=teacher_id)
        rows = rows.order_by('group__group_name', 'student__full_name')
        detail_page = Paginator(rows, 50).get_page(request.GET.get('dpage'))
    else:
        detail_kind = ''

    context = {
        'page_title': 'التقرير الشامل',
        'range_qs': _urlencode(range_params),
        'base_qs': _urlencode(base_params),
        'detail_kind': detail_kind,
        'detail_title': detail_title,
        'detail_type': detail_type,
        'detail_page': detail_page,
        'selected_group_obj': groups_by_id.get(group_id) if group_id is not None else None,
        'att_attended': attended,
        'date_from': date_from,
        'date_to': date_to,
        'default_from': default_from,
        'selected_group': group_id,
        'selected_teacher': teacher_id,
        'groups': Group.objects.filter(is_active=True).select_related('teacher').order_by('group_name'),
        'teachers': Teacher.objects.filter(is_active=True).order_by('full_name'),
        'total_due': total_due,
        'total_paid': total_paid,
        'total_remaining': total_due - total_paid,
        'collection_rate': round(_rate(total_paid, total_due), 1),
        'total_students': totals['students'] or 0,
        'payment_rows': totals['rows'] or 0,
        'sessions_count': sessions_count,
        'att_present': att_totals['present'] or 0,
        'att_late': att_totals['late'] or 0,
        'att_absent': att_totals['absent'] or 0,
        'attendance_rate': round(_rate(attended, att_total), 1),
        'breakdown': breakdown,
    }
    return render(request, 'reports/comprehensive.html', context)
