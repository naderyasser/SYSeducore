from datetime import date

from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts.decorators import admin_required, supervisor_required
from apps.teachers.models import Group, Teacher

from .models import Payment
from .pricing import base_fee_parts
from .services import SettlementService


def _ensure_cycle_payments():
    """
    Fill in the missing ``Payment`` row for anyone enrolled in a **cycle-billed**
    group (``sessions_per_month > 0``) who has none on that group's open cycle
    — priced for the lesson they are actually joining at.

    Rows for a cycle are normally created in bulk by
    ``apps.attendance.tasks.roll_group_cycles`` the moment the cycle opens, so
    the gap this fills is the student who enrolled *after* it opened: exactly
    the late joiner whose invoice must be pro-rated. The set is therefore small
    (new enrollments only), which is what makes the per-student
    ``billing_start_sequence`` lookup here affordable.

    This replaces what ``_ensure_monthly_payments`` used to do for these
    groups. That function billed by calendar month at the full fee and left
    ``cycle`` null — and since the uniqueness constraint is on
    ``(student, cycle)`` and NULL never collides, it happily added a second,
    full-price, month-shaped invoice next to the correct pro-rated cycle one
    every time a cycle had started in an earlier month. Money owed on screen
    then had to be reconciled against the cycle by hand.
    """
    from apps.attendance.entitlement import billing_start_sequence
    from apps.payments.pricing import entitled_sessions, prorated_fee
    from apps.students.models import StudentGroupEnrollment
    from apps.teachers.cycles import open_cycle_for

    enrollments = (
        StudentGroupEnrollment.objects
        .filter(
            is_active=True,
            student__deleted_at__isnull=True,
            group__deleted_at__isnull=True,
            group__is_active=True,
            group__sessions_per_month__gt=0,
        )
        .select_related('student', 'group')
    )

    by_group = {}
    for enrollment in enrollments:
        by_group.setdefault(enrollment.group, []).append(enrollment)

    created = 0
    for group, group_enrollments in by_group.items():
        cycle = open_cycle_for(group)
        already = set(
            Payment.objects.filter(
                cycle=cycle,
                student_id__in=[e.student_id for e in group_enrollments],
            ).values_list('student_id', flat=True)
        )
        for enrollment in group_enrollments:
            if enrollment.student_id in already:
                continue
            start_seq = billing_start_sequence(enrollment.student, cycle)
            fee = prorated_fee(
                enrollment, cycle_size=cycle.sessions_planned,
                first_sequence=start_seq, group=group,
            )
            Payment.objects.create(
                student=enrollment.student,
                group=group,
                cycle=cycle,
                month=(cycle.started_on or timezone.localdate()).replace(day=1),
                amount_due=fee,
                amount_paid=0,
                # A zero fee is an exemption, not a collection — the same rule
                # ``Payment.save()`` enforces for the monthly rows below.
                status='paid' if fee <= 0 else 'unpaid',
                is_exempt=fee <= 0,
                sessions_total=entitled_sessions(
                    cycle_size=cycle.sessions_planned, first_sequence=start_seq,
                ),
            )
            created += 1

    return created


def _ensure_monthly_payments(month_date):
    """
    Auto-generate Payment rows for every active enrollment in a group that is
    **not** cycle-billed (``sessions_per_month == 0``) and does not already
    have one for *month_date*.

    Cycle-billed groups are deliberately excluded and handled by
    :func:`_ensure_cycle_payments` instead: billing them by calendar month is
    the "charge a full month, refund the difference on paper" behaviour that
    session billing exists to replace.

    **Current month only.** Callers must never pass a historical month: the
    fees used here are today's fees, so back-filling an old month would
    invent an accounting history that never happened (a user browsing to
    ``?month=2020-01`` used to create a full set of January-2020 rows priced
    at current fees). :func:`payment_list` enforces this.

    The missing enrollments are found with a single ``NOT EXISTS`` query
    instead of walking every active enrollment in Python, so the normal case
    — nothing to create — costs one cheap query that returns no rows.

    Returns the number of newly created payment records.
    """
    from apps.students.models import StudentGroupEnrollment

    already_billed = Payment.objects.filter(
        month=month_date,
        student_id=OuterRef('student_id'),
        group_id=OuterRef('group_id'),
    )

    missing = (
        StudentGroupEnrollment.objects
        .filter(is_active=True)
        # Soft-deleted students/groups must not be billed, nor a group that
        # was deactivated (closed) — its enrollments stay active but it no
        # longer runs.
        .filter(
            student__deleted_at__isnull=True,
            group__deleted_at__isnull=True,
            group__is_active=True,
            # Cycle-billed groups are billed per cycle, never per month.
            group__sessions_per_month=0,
        )
        .annotate(has_payment=Exists(already_billed))
        .filter(has_payment=False)
        .values_list(
            'student_id', 'group_id', 'financial_status',
            'custom_fee', 'group__standard_fee',
        )
    )

    to_create = []
    for student_id, group_id, financial_status, custom_fee, standard_fee in missing:
        fee = base_fee_parts(financial_status, custom_fee, standard_fee)

        if fee <= 0:
            # Zero-fee row: still created so the scanner finds a record, but
            # flagged ``is_exempt`` so it is not counted as a collection.
            to_create.append(Payment(
                student_id=student_id,
                group_id=group_id,
                month=month_date,
                amount_due=0,
                amount_paid=0,
                status='paid',
                is_exempt=True,
            ))
        else:
            to_create.append(Payment(
                student_id=student_id,
                group_id=group_id,
                month=month_date,
                amount_due=fee,
                amount_paid=0,
                status='unpaid',
            ))

    if to_create:
        Payment.objects.bulk_create(to_create, ignore_conflicts=True)

    return len(to_create)


@supervisor_required
def payment_list(request):
    """
    List payments with filters. Defaults to current month unpaid/partial.
    Auto-generates payment records for active enrollments — **for the
    current month only** — so every student appears in the list.
    """
    # Use localtime (Cairo) so the month matches what the scanner expects
    current_month = timezone.localdate().replace(day=1)

    # Filter params
    month_filter = request.GET.get('month', current_month.strftime('%Y-%m'))
    status_filter = request.GET.get('status', '')
    group_filter = request.GET.get('group', '')
    search = request.GET.get('search', '')

    try:
        month_date = date(int(month_filter[:4]), int(month_filter[5:7]), 1)
    except (TypeError, ValueError):
        month_date = current_month

    # ── Auto-generate missing payment rows — current month only ──
    # Browsing an archived month must never write to it.
    if month_date == current_month:
        _ensure_cycle_payments()
        _ensure_monthly_payments(month_date)

    scope = Payment.objects.filter(student__deleted_at__isnull=True)

    if month_date == current_month:
        # A cycle is 8 lessons, not a calendar month, so one routinely starts
        # in one month and is still being collected in the next. Filtering the
        # live screen on ``month`` alone would drop those students off it —
        # the desk would stop seeing real, unpaid dues the moment the month
        # rolled over. The current month therefore shows this month's rows
        # *plus* every still-open cycle.
        scope = scope.filter(
            Q(month=month_date) | Q(cycle__isnull=False, cycle__closed_on__isnull=True)
        )
    else:
        # An archived month is read as it stood: only its own rows.
        scope = scope.filter(month=month_date)

    # The list and the stat tiles must be built from the same ``scope``, or
    # the totals describe a different set of rows than the table under them.
    payments = scope.select_related('student', 'group', 'group__teacher')

    if status_filter:
        payments = payments.filter(status=status_filter)
    if group_filter:
        payments = payments.filter(group_id=group_filter)
    if search:
        payments = payments.filter(
            Q(student__full_name__icontains=search) |
            Q(student__student_code__icontains=search) |
            Q(student__parent_phone__icontains=search)
        )

    payments = payments.order_by('status', 'student__full_name')

    # Stats for the selected month — one aggregate query instead of four
    # counts. Exempt (zero-fee) rows carry status='paid' so the scanner lets
    # them in, but they are *not* a collection: they are counted separately
    # and excluded from the collection rate.
    #
    # ``amount_due``/``amount_collected``/``collection_rate`` are cumulative
    # money figures — admin only (``show_financials``). The status counts
    # (paid/partial/unpaid/total) are per-payment desk data and stay visible
    # to supervisors; ``templates/payments/list.html`` only ever renders
    # those four keys, so gating the rest costs nothing today but stops a
    # future template change from leaking them to a non-admin by accident.
    show_financials = request.user.can_see_financials()
    billable = Q(is_exempt=False)
    agg_kwargs = dict(
        paid=Count('pk', filter=billable & Q(status='paid')),
        partial=Count('pk', filter=billable & Q(status='partial')),
        unpaid=Count('pk', filter=billable & Q(status='unpaid')),
        exempt=Count('pk', filter=Q(is_exempt=True)),
        billable_total=Count('pk', filter=billable),
        total=Count('pk'),
    )
    if show_financials:
        agg_kwargs['amount_due'] = Sum('amount_due', filter=billable)
        agg_kwargs['amount_collected'] = Sum('amount_paid', filter=billable)
    stats = scope.aggregate(**agg_kwargs)
    if show_financials:
        for key in ('amount_due', 'amount_collected'):
            stats[key] = stats[key] or 0
        stats['collection_rate'] = (
            round(stats['paid'] * 100 / stats['billable_total'], 1)
            if stats['billable_total'] else 0
        )

    groups = Group.objects.filter(is_active=True).select_related('teacher')

    context = {
        'payments': payments,
        'stats': stats,
        'show_financials': show_financials,
        'groups': groups,
        'current_month': month_date,
        'is_current_month': month_date == current_month,
        'month_filter': month_filter,
        'status_filter': status_filter,
        'group_filter': group_filter,
        'search': search,
    }
    return render(request, 'payments/list.html', context)


@admin_required
def teacher_settlement(request, teacher_id):
    """
    Show teacher settlement for a specific month.

    Settlement exposes the centre's revenue split and every teacher's
    payout — an accounting function, not a desk operation, so it is
    admin-only.
    """
    teacher = get_object_or_404(Teacher, pk=teacher_id)

    if request.method == 'POST':
        today = timezone.localdate()
        try:
            year = int(request.POST.get('year', today.year))
            month = int(request.POST.get('month', today.month))
        except (TypeError, ValueError):
            return JsonResponse(
                {'success': False, 'message': 'الشهر أو السنة غير صالحة'},
                status=400,
            )
        if not 1 <= month <= 12 or not 2000 <= year <= 2200:
            return JsonResponse(
                {'success': False, 'message': 'الشهر أو السنة غير صالحة'},
                status=400,
            )

        result = SettlementService.calculate_teacher_settlement(teacher_id, year, month)

        if result['success']:
            return render(request, 'payments/settlement.html', {
                'teacher': teacher,
                'settlement': result['data']
            })
        return JsonResponse(result, status=400)

    return render(request, 'payments/settlement.html', {'teacher': teacher})


# ─────────────────────────────────────────────────────────────
# Persisted, editable, approvable teacher settlement sheet
# ─────────────────────────────────────────────────────────────

@admin_required
def settlement_index(request):
    """
    اختيار مدرس وفترة لبناء/فتح كشف تصفية، بجانب آخر الكشوفات المُنشأة.
    """
    from .models import TeacherSettlement

    teachers = Teacher.objects.filter(is_active=True).order_by('full_name')

    # ``?teacher=<id>`` arrives from the "تصفية حساب المدرس" button on a
    # teacher's own page: preselect that teacher (and show only their previous
    # sheets) so settling one teacher is one click from their file instead of
    # landing on a blank picker and hunting for the name again.
    selected_teacher = None
    raw_teacher = request.GET.get('teacher')
    if raw_teacher:
        try:
            selected_teacher = int(raw_teacher)
        except (TypeError, ValueError):
            selected_teacher = None

    recent = TeacherSettlement.objects.select_related('teacher')
    if selected_teacher is not None:
        recent = recent.filter(teacher_id=selected_teacher)
    # Sliced last — a queryset cannot be filtered once a slice has been taken.
    recent = recent.order_by('-created_at')[:20]

    return render(request, 'payments/settlement_index.html', {
        'teachers': teachers,
        'recent_settlements': recent,
        'selected_teacher': selected_teacher,
    })


@admin_required
def settlement_detail(request, settlement_id):
    """عرض/تعديل كشف تصفية محدد."""
    from .models import TeacherSettlement

    settlement = get_object_or_404(
        TeacherSettlement.objects.select_related('teacher'), pk=settlement_id,
    )
    lines = (
        settlement.lines.select_related('group', 'student')
        .order_by('group__group_name', 'student__full_name')
    )

    groups = {}
    for line in lines:
        groups.setdefault(line.group, []).append(line)

    return render(request, 'payments/settlement_detail.html', {
        'settlement': settlement,
        'groups': groups,
    })


@admin_required
def settlement_print(request, settlement_id):
    """نسخة قابلة للطباعة من كشف التصفية."""
    from .models import TeacherSettlement

    settlement = get_object_or_404(
        TeacherSettlement.objects.select_related('teacher'), pk=settlement_id,
    )
    lines = (
        settlement.lines.select_related('group', 'student')
        .order_by('group__group_name', 'student__full_name')
    )
    groups = {}
    for line in lines:
        groups.setdefault(line.group, []).append(line)

    return render(request, 'payments/settlement_print.html', {
        'settlement': settlement,
        'groups': groups,
        'printed_at': timezone.localtime(),
    })
