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
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
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
from apps.teachers.models import Group, Room, Teacher

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
            'date': day.strftime('%a'),
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
        month_totals = _month_filter(Payment.objects.all(), this_month_start).aggregate(
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
    today_schedule = []
    for grp in active_groups:
        for entry in grp.get_schedule_entries():
            if entry.day_of_week != current_day_name:
                continue
            enrolled_count = enrolment_counts.get(grp.pk, 0)
            capacity = entry.room.capacity if entry.room else 0
            end_time = entry.get_end_time()

            session_status = 'upcoming'
            if current_time > end_time:
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
        'today_day_name': current_day_name,
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
    payments = Payment.objects.select_related(
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
            Payment.objects
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
            'month_name': month_date.strftime('%B %Y'),
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
    revenue = dict(
        Payment.objects.filter(group__teacher_id__in=teacher_ids)
        .values_list('group__teacher_id')
        .annotate(total=Sum('amount_paid'))
        .order_by()
        .values_list('group__teacher_id', 'total')
    )

    teacher_stats = [
        {
            'name': teacher.full_name,
            'groups_count': group_counts.get(teacher.pk, 0),
            'total_revenue': revenue.get(teacher.pk) or 0,
            'is_active': teacher.is_active,
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
    payments_qs = Payment.objects.filter(month=report_month).select_related(
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

    # --- Payment records (paginated) ---
    paginator = Paginator(payments_qs, 30)
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
        'monthly_data_json': json.dumps(group_breakdown, ensure_ascii=False, default=str),
    }

    return render(request, 'reports/tsfya.html', context)
