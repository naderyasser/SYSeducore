from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Prefetch
from django.db import models, transaction, IntegrityError
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from datetime import timedelta
from decimal import Decimal
import json
import logging

from .models import Student, StudentGroupEnrollment
from .forms import StudentForm
from .utils import enrollment_compatibility_errors, normalize_financial_status, parse_money
from apps.teachers.models import Group
from apps.accounts.decorators import (
    ajax_login_required,
    ajax_supervisor_required,
    supervisor_required,
)
from apps.attendance.models import Attendance, ActivityLog
from apps.payments.models import Payment

logger = logging.getLogger(__name__)

#: Students shown per page in the HTML list view.
STUDENTS_PER_PAGE = 25


@login_required
def student_list(request):
    """
    List all students with filtering and search functionality.
    View as table with barcode display and action buttons.
    """
    # Get filter parameters
    search = request.GET.get('search', '')
    group_filter = request.GET.get('group', '')
    status_filter = request.GET.get('status', '')
    gender_filter = request.GET.get('gender', '')
    education_stage_filter = request.GET.get('education_stage', '')

    # Build query with annotations.
    # NOTE: counting 'groups' (M2M) while filtering on 'group_enrollments'
    # (reverse FK) joins two independent relations and multiplies the rows —
    # the count was wrong for every student in more than one group, and the
    # with_groups/no_groups filters below are built on it. Count the enrollment
    # rows themselves instead.
    students = Student.objects.all().annotate(
        groups_count=Count(
            'group_enrollments',
            filter=Q(group_enrollments__is_active=True),
            distinct=True,
        )
    ).prefetch_related(
        Prefetch(
            'group_enrollments',
            queryset=StudentGroupEnrollment.objects.filter(
                is_active=True
            ).select_related('group', 'group__teacher').prefetch_related('group__schedules__room')[:3],
            to_attr='active_enrollments'
        )
    )

    # Apply search filter
    if search:
        students = students.filter(
            Q(full_name__icontains=search) |
            Q(student_code__icontains=search) |
            Q(parent_phone__icontains=search) |
            Q(parent_name__icontains=search) |
            Q(school_name__icontains=search)
        )

    # Apply group filter (ignore non-numeric junk instead of letting the ORM
    # raise ValueError trying to cast it to the group_id field)
    if group_filter and str(group_filter).isdigit():
        students = students.filter(
            group_enrollments__group_id=group_filter,
            group_enrollments__is_active=True,
        ).distinct()

    # Apply status filter
    if status_filter == 'with_groups':
        students = students.filter(groups_count__gt=0)
    elif status_filter == 'no_groups':
        students = students.filter(groups_count=0)
    elif status_filter == 'active':
        students = students.filter(is_active=True)
    elif status_filter == 'inactive':
        students = students.filter(is_active=False)

    # Apply gender filter
    if gender_filter:
        students = students.filter(gender=gender_filter)

    # Apply education stage filter
    if education_stage_filter:
        students = students.filter(education_stage=education_stage_filter)

    # Order by most recent first (stable secondary key so pagination cannot
    # show the same student on two pages when created_at ties)
    students = students.order_by('-created_at', '-student_id')

    # Paginate: the view used to materialise EVERY student and then loop over
    # them in Python (and the template renders a barcode per row).
    paginator = Paginator(students, STUDENTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Add payment status for current month (use localtime to match scanner) —
    # only for the students actually on this page.
    current_month = timezone.localdate().replace(day=1)
    page_student_ids = [s.student_id for s in page_obj.object_list]
    paid_student_ids = set(
        Payment.objects.filter(
            student_id__in=page_student_ids,
            month=current_month,
            status='paid'
        ).values_list('student_id', flat=True)
    )
    for student in page_obj.object_list:
        student.has_paid_current_month = student.student_id in paid_student_ids

    # Querystring without 'page' so pagination links keep the active filters
    querydict = request.GET.copy()
    querydict.pop('page', None)
    filter_querystring = querydict.urlencode()

    # Get all groups for filter dropdown
    all_groups = Group.objects.filter(is_active=True).select_related('teacher')

    # Statistics
    stats = {
        'total': Student.objects.filter(is_active=True).count(),
        'with_groups': Student.objects.filter(
            is_active=True,
            group_enrollments__is_active=True
        ).distinct().count(),
        'without_groups': Student.objects.filter(
            is_active=True
        ).exclude(
            group_enrollments__is_active=True
        ).count(),
        'recent': Student.objects.filter(
            is_active=True,
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()
    }

    context = {
        # 'students' stays the iterable the template loops over (now a Page);
        # 'page_obj'/'paginator' drive the pagination controls.
        'students': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'filter_querystring': filter_querystring,
        'all_groups': all_groups,
        'stats': stats,
        'current_search': search,
        'current_group': group_filter,
        'current_status': status_filter,
        'current_gender': gender_filter,
        'current_education_stage': education_stage_filter,
    }

    return render(request, 'students/list.html', context)


@login_required
def student_detail(request, student_id):
    """
    Show student details with all related information.
    """
    student = get_object_or_404(Student, pk=student_id)

    # Get active enrollments
    active_enrollments = StudentGroupEnrollment.objects.filter(
        student=student,
        is_active=True
    ).select_related('group', 'group__teacher').prefetch_related('group__schedules__room')

    # Get recent attendance (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_attendance = Attendance.objects.filter(
        student=student,
        scan_time__gte=thirty_days_ago
    ).order_by('-scan_time')[:20]

    # Attendance statistics (single query with conditional aggregation)
    attendance_agg = Attendance.objects.filter(
        student=student,
        scan_time__gte=thirty_days_ago
    ).aggregate(
        present=Count('pk', filter=Q(status='present')),
        late=Count('pk', filter=Q(status='late')),
        absent=Count('pk', filter=Q(status='absent')),
    )
    attendance_stats = attendance_agg

    # Get available groups (not enrolled in) - filtered by student's gender and education stage
    enrolled_group_ids = active_enrollments.values_list('group_id', flat=True)
    available_groups = Group.objects.filter(
        is_active=True
    ).exclude(
        group_id__in=enrolled_group_ids
    ).select_related('teacher')

    # Filter by gender compatibility
    if student.gender == 'male':
        available_groups = available_groups.exclude(gender_type='female')
    elif student.gender == 'female':
        available_groups = available_groups.exclude(gender_type='male')

    # Filter by education stage and year if set
    if student.education_stage:
        available_groups = available_groups.filter(
            models.Q(education_stage=student.education_stage) |
            models.Q(education_stage='')
        )
    if student.education_year:
        available_groups = available_groups.filter(
            models.Q(education_year=student.education_year) |
            models.Q(education_year='')
        )

    context = {
        'student': student,
        'active_enrollments': active_enrollments,
        'recent_attendance': recent_attendance,
        'attendance_stats': attendance_stats,
        'available_groups': available_groups,
    }

    return render(request, 'students/detail.html', context)


def _teachers_of(groups):
    """
    The distinct teachers behind ``groups``, for the registration form's
    "المدرس" filter.

    The template used to build that dropdown by looping over the groups
    themselves, so a teacher with three groups was listed three times — on the
    very screen where a teacher is picked before their group is.

    Takes the already-evaluated ``groups`` list rather than issuing its own
    query: the caller has just selected them with ``select_related('teacher')``.
    """
    seen = {}
    for group in groups:
        if group.teacher_id and group.teacher_id not in seen:
            seen[group.teacher_id] = group.teacher
    return sorted(seen.values(), key=lambda t: t.full_name)


@supervisor_required
def student_create(request):
    """
    Create a new student with auto-generated code.
    """
    groups = Group.objects.filter(is_active=True).select_related('teacher')

    if request.method == 'POST':
        form = StudentForm(request.POST)

        # Get selected groups
        selected_groups = request.POST.getlist('groups')

        if form.is_valid():
            try:
                with transaction.atomic():
                    # An empty code is generated (and retried on collision) by
                    # Student.save() itself — see models.CODE_GENERATION_ATTEMPTS.
                    student = form.save()

                    # Add to selected groups if any, with financial status
                    # (mirror student_update: drop non-numeric ids instead of
                    # letting Group.objects.get(pk=...) raise ValueError)
                    for group_id in {int(g) for g in selected_groups if g.isdigit()}:
                        try:
                            group = Group.objects.get(pk=group_id)
                            compatibility_errors = enrollment_compatibility_errors(student, group)
                            if compatibility_errors:
                                for error in compatibility_errors:
                                    messages.error(request, error)
                                continue
                            financial_status = normalize_financial_status(
                                request.POST.get(f'financial_status_{group_id}', 'normal')
                            )
                            custom_fee = None
                            if financial_status == 'symbolic':
                                custom_fee = parse_money(
                                    request.POST.get(f'custom_fee_{group_id}')
                                )
                            StudentGroupEnrollment.objects.create(
                                student=student,
                                group=group,
                                financial_status=financial_status,
                                custom_fee=custom_fee,
                                is_active=True
                            )

                            # Handle initial payment if provided (Decimal only —
                            # float money silently reintroduces rounding errors).
                            # Routed through the ledger (record_transaction) and
                            # apps.payments.activation.activate_payment instead of
                            # writing amount_paid/status directly — a direct write
                            # leaves no PaymentTransaction receipt behind it.
                            amount = parse_money(request.POST.get(f'initial_payment_{group_id}'))
                            if amount and amount > 0:
                                from apps.payments.pricing import base_fee_parts
                                from apps.payments.activation import activate_payment
                                from apps.teachers.cycles import open_cycle_for

                                # تاريخ الاشتراك: optional. A blank (or
                                # unparseable) value must never block the
                                # registration — the desk very often registers a
                                # student without being told the exact date, and
                                # a required field there just gets filled with a
                                # wrong date to get past it.
                                paid_on = None
                                raw_paid_on = request.POST.get(f'paid_on_{group_id}')
                                if raw_paid_on:
                                    try:
                                        from datetime import date as _date
                                        paid_on = _date.fromisoformat(raw_paid_on)
                                    except ValueError:
                                        paid_on = None

                                amount_due = base_fee_parts(
                                    financial_status, custom_fee, group.standard_fee,
                                )
                                cycle = open_cycle_for(group) if group.sessions_per_month else None
                                if paid_on is None:
                                    # Fall back to the cycle the money is
                                    # actually buying — a student registered on
                                    # the 5th for a cycle that opened on the 1st
                                    # belongs to that cycle's period on the
                                    # teacher's settlement, not to today's.
                                    # A future-dated cycle (or no cycle at all)
                                    # falls through to today, so the ledger can
                                    # never be stamped with a date that has not
                                    # happened yet.
                                    today = timezone.localdate()
                                    cycle_start = cycle.started_on if cycle else None
                                    paid_on = (
                                        cycle_start
                                        if cycle_start and cycle_start <= today
                                        else today
                                    )
                                payment = Payment.objects.create(
                                    student=student,
                                    group=group,
                                    cycle=cycle,
                                    month=(
                                        (cycle.started_on or timezone.localdate()).replace(day=1)
                                        if cycle else timezone.localdate().replace(day=1)
                                    ),
                                    amount_due=amount_due,
                                    sessions_total=cycle.sessions_planned if cycle else 4,
                                )
                                # record_transaction rejects a total above
                                # amount_due (system-wide rule, unlike the old
                                # direct-write path which silently accepted
                                # any typed amount) — clamp instead of letting
                                # a receptionist's rounding/typo 500 the page.
                                payment.record_transaction(
                                    min(amount, amount_due), user=request.user,
                                    note='دفعة عند التسجيل', effective_on=paid_on,
                                )
                                if payment.status == 'paid':
                                    activate_payment(
                                        payment, paid_on=paid_on, user=request.user, request=request,
                                    )
                        except Group.DoesNotExist:
                            pass

            except IntegrityError as e:
                logger.exception('Failed to create student (POST by user %s)', request.user.pk)
                if 'student_code' in str(e).lower() or 'unique' in str(e).lower():
                    messages.error(request, 'حدث تعارض في رقم الكود بسبب إضافة متزامنة. يرجى المحاولة مرة أخرى.')
                else:
                    messages.error(request, 'حدث خطأ أثناء حفظ البيانات. يرجى المحاولة مرة أخرى.')
                return render(request, 'students/form.html', {
                    'form': form,
                    'groups': groups,
                    'teachers': _teachers_of(groups),
                    'is_create': True
                })

            # Generate QR code image (non-critical: the card view renders the
            # barcode on the fly, but a persistent failure must be visible)
            try:
                student.save_barcode_image()
            except Exception:
                logger.exception(
                    'Failed to save barcode image for student %s (code=%s)',
                    student.pk, student.student_code,
                )

            # Activity logging
            ActivityLog.log(
                user=request.user,
                action='student_create',
                description=f'إنشاء طالب جديد: {student.full_name} (كود: {student.student_code})',
                target_model='Student',
                target_id=student.student_id,
                request=request
            )

            messages.success(
                request,
                f'تم إضافة الطالب بنجاح. كود الطالب: {student.student_code}'
            )
            return redirect('students:detail', student_id=student.student_id)
    else:
        form = StudentForm()

    return render(request, 'students/form.html', {
        'form': form,
        'groups': groups,
        'teachers': _teachers_of(groups),
        'is_create': True
    })


@supervisor_required
def student_update(request, student_id):
    """
    Update an existing student.
    """
    student = get_object_or_404(Student, pk=student_id)
    groups = Group.objects.filter(is_active=True).select_related('teacher')

    # Get currently enrolled groups
    current_enrollments = StudentGroupEnrollment.objects.filter(
        student=student,
        is_active=True
    )
    current_group_ids = set(current_enrollments.values_list('group_id', flat=True))
    
    # Build enrollment data for template (financial status per group)
    enrollment_data = {}
    for enrollment in current_enrollments:
        enrollment_data[enrollment.group_id] = {
            'financial_status': enrollment.financial_status,
            'custom_fee': str(enrollment.custom_fee) if enrollment.custom_fee else '',
        }

    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)

        # Get selected groups
        selected_groups = request.POST.getlist('groups')
        selected_group_ids = set(int(g) for g in selected_groups if g.isdigit())

        if form.is_valid():
            with transaction.atomic():
                form.save()

                # Create / re-activate / update every selected enrollment.
                #
                # This used to iterate ``selected - current`` and call
                # get_or_create(): a group the student had been *removed* from
                # is not in ``current_group_ids`` (that set only holds active
                # rows), so it looked new, get_or_create GOT the inactive row
                # and ignored ``defaults`` — the student was never re-enrolled.
                # Financial edits to rows that stayed selected were dropped on
                # the floor for the same reason. Both are handled here.
                for group_id in selected_group_ids:
                    try:
                        group = Group.objects.get(pk=group_id)
                    except Group.DoesNotExist:
                        continue

                    compatibility_errors = enrollment_compatibility_errors(student, group)
                    if compatibility_errors:
                        for error in compatibility_errors:
                            messages.error(request, error)
                        continue

                    posted_status = request.POST.get(f'financial_status_{group_id}')
                    financial_status = normalize_financial_status(posted_status or 'normal')
                    custom_fee = None
                    if financial_status == 'symbolic':
                        custom_fee = parse_money(request.POST.get(f'custom_fee_{group_id}'))

                    enrollment, created = StudentGroupEnrollment.objects.get_or_create(
                        student=student,
                        group=group,
                        defaults={
                            'financial_status': financial_status,
                            'custom_fee': custom_fee,
                            'is_active': True
                        }
                    )
                    if not created:
                        updated_fields = []
                        # Only overwrite the financial terms when the request
                        # actually carried them, so a caller that posts nothing
                        # cannot silently reset an exemption to 'normal'.
                        if posted_status is not None:
                            enrollment.financial_status = financial_status
                            enrollment.custom_fee = custom_fee
                            updated_fields += ['financial_status', 'custom_fee']
                        if not enrollment.is_active:
                            enrollment.is_active = True
                            updated_fields.append('is_active')
                        if updated_fields:
                            enrollment.save(update_fields=updated_fields)

                # Deactivate removed enrollments
                for group_id in current_group_ids - selected_group_ids:
                    StudentGroupEnrollment.objects.filter(
                        student=student,
                        group_id=group_id
                    ).update(is_active=False)

            ActivityLog.log(
                user=request.user, action='student_update',
                description=f'تعديل بيانات الطالب: {student.full_name} (كود: {student.student_code})',
                target_model='Student', target_id=student.student_id, request=request
            )
            messages.success(request, 'تم تحديث بيانات الطالب بنجاح')
            return redirect('students:detail', student_id=student.student_id)
    else:
        form = StudentForm(instance=student)

    return render(request, 'students/form.html', {
        'form': form,
        'student': student,
        'groups': groups,
        'teachers': _teachers_of(groups),
        'current_group_ids': current_group_ids,
        'enrollment_data_json': json.dumps(enrollment_data),
        'is_create': False
    })


@supervisor_required
def student_delete(request, student_id):
    """
    Soft delete a student (move to recycle bin).
    """
    student = get_object_or_404(Student, pk=student_id)

    if request.method == 'POST':
        with transaction.atomic():
            student.soft_delete(user=request.user)
            # Enrollments are queried directly by the auto-absence and
            # notification crons, which join through the FK and never look at
            # student.deleted_at — a deleted student kept collecting absences
            # and WhatsApp messages. Deactivate them with the student.
            StudentGroupEnrollment.objects.filter(
                student=student, is_active=True,
            ).update(is_active=False)

        # Log the deletion
        ActivityLog.log(
            user=request.user,
            action='student_delete',
            description=f'حذف طالب (سلة المهملات): {student.full_name} (كود: {student.student_code})',
            target_model='Student',
            target_id=student.student_id,
            request=request
        )
        
        messages.success(request, f'تم نقل الطالب "{student.full_name}" إلى سلة المهملات')
        return redirect('students:list')

    return render(request, 'students/delete_confirm.html', {'student': student})


@login_required
def student_id_card(request, student_id):
    """
    Display printable ID card for a student.
    Professional ID card with student data.
    """
    student = get_object_or_404(Student, pk=student_id)

    # Get active enrollments (max 3 for card)
    active_enrollments = StudentGroupEnrollment.objects.filter(
        student=student,
        is_active=True
    ).select_related('group', 'group__teacher').prefetch_related('group__schedules__room')[:3]

    # Generate barcode base64 for the card
    barcode_base64 = student.get_barcode_base64()

    context = {
        'student': student,
        'enrollments': active_enrollments,
        'barcode_base64': barcode_base64,
        'today': timezone.localdate(),
    }

    return render(request, 'students/id_card.html', context)


@login_required
def student_id_card_print(request, student_id):
    """
    Print-ready ID card page.
    """
    student = get_object_or_404(Student, pk=student_id)

    active_enrollments = StudentGroupEnrollment.objects.filter(
        student=student,
        is_active=True
    ).select_related('group', 'group__teacher').prefetch_related('group__schedules__room')[:3]

    barcode_base64 = student.get_barcode_base64()

    context = {
        'student': student,
        'enrollments': active_enrollments,
        'barcode_base64': barcode_base64,
        'today': timezone.localdate(),
        'print_mode': True
    }

    return render(request, 'students/id_card_print.html', context)


@login_required
def student_qr_ticket(request, student_id):
    """
    طباعة تذكرة QR صغيرة (~5 × 8 سم) تحتوي فقط على كود الطالب و QR.
    Deprecated: use qr_ticket_pdf for reliable repeat printing.
    """
    student = get_object_or_404(Student, pk=student_id)
    barcode_base64 = student.get_barcode_base64()
    return render(request, 'students/qr_ticket.html', {
        'student': student,
        'barcode_base64': barcode_base64,
    })


@login_required
def qr_ticket_pdf(request, student_id):
    """
    Server-side PDF sticker (35mm x 10mm) — no browser caching issues.
    """
    from .services.sticker_pdf import build_sticker_pdf
    student = get_object_or_404(Student, pk=student_id)
    pdf = build_sticker_pdf(student)
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="sticker_{student.student_code}.pdf"'
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp['Pragma'] = 'no-cache'
    resp['Expires'] = '0'
    return resp


@ajax_login_required
def get_next_code(request):
    """
    API endpoint to get next auto-generated student code.
    """
    next_code = Student.generate_next_code()
    return JsonResponse({
        'success': True,
        'next_code': next_code
    })


@ajax_supervisor_required
def student_toggle_status(request, student_id):
    """
    Toggle student active status.

    Deactivating a student stops them entering the centre, so this is a desk
    operation (supervisor+) exactly like create/update/delete — it used to be
    open to any authenticated account, including 'teacher'.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    student = get_object_or_404(Student, pk=student_id)
    student.is_active = not student.is_active
    student.save()

    status_text = 'تفعيل' if student.is_active else 'تعطيل'
    ActivityLog.log(
        user=request.user, action='student_toggle',
        description=f'{status_text} طالب: {student.full_name} (كود: {student.student_code})',
        target_model='Student', target_id=student.student_id, request=request
    )

    return JsonResponse({
        'success': True,
        'is_active': student.is_active,
        'message': 'تم تحديث الحالة بنجاح'
    })
