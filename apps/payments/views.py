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


def _ensure_monthly_payments(month_date):
    """
    Auto-generate Payment rows for every active enrollment that does not
    already have one for *month_date*.

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
        _ensure_monthly_payments(month_date)

    payments = Payment.objects.select_related(
        'student', 'group', 'group__teacher'
    ).filter(month=month_date, student__deleted_at__isnull=True)

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
    stats = Payment.objects.filter(
        month=month_date, student__deleted_at__isnull=True,
    ).aggregate(**agg_kwargs)
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
    recent = (
        TeacherSettlement.objects.select_related('teacher')
        .order_by('-created_at')[:20]
    )
    return render(request, 'payments/settlement_index.html', {
        'teachers': teachers,
        'recent_settlements': recent,
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
