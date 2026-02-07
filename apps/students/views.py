from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, Prefetch
from django.db import models
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from datetime import timedelta
import json

from .models import Student, StudentGroupEnrollment
from .forms import StudentForm, StudentQuickForm
from apps.teachers.models import Group
from apps.accounts.decorators import supervisor_required
from apps.attendance.models import Attendance, ActivityLog


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

    # Build query with annotations
    students = Student.objects.all().annotate(
        groups_count=Count(
            'groups',
            filter=Q(group_enrollments__is_active=True)
        )
    ).prefetch_related(
        Prefetch(
            'group_enrollments',
            queryset=StudentGroupEnrollment.objects.filter(
                is_active=True
            ).select_related('group', 'group__teacher', 'group__room')[:3],
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

    # Apply group filter
    if group_filter:
        students = students.filter(groups__group_id=group_filter)

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

    # Order by most recent first
    students = students.order_by('-created_at')

    # Get all groups for filter dropdown
    all_groups = Group.objects.filter(is_active=True).select_related('teacher')

    # Statistics
    stats = {
        'total': Student.objects.filter(is_active=True).count(),
        'with_groups': Student.objects.filter(
            is_active=True,
            groups__is_active=True
        ).distinct().count(),
        'without_groups': Student.objects.filter(
            is_active=True
        ).exclude(
            groups__is_active=True
        ).count(),
        'recent': Student.objects.filter(
            is_active=True,
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()
    }

    context = {
        'students': students,
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
    ).select_related('group', 'group__teacher', 'group__room')

    # Get recent attendance (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_attendance = Attendance.objects.filter(
        student=student,
        scan_time__gte=thirty_days_ago
    ).order_by('-scan_time')[:20]

    # Attendance statistics
    attendance_stats = {
        'present': Attendance.objects.filter(
            student=student,
            status='present',
            scan_time__gte=thirty_days_ago
        ).count(),
        'late': Attendance.objects.filter(
            student=student,
            status='late',
            scan_time__gte=thirty_days_ago
        ).count(),
        'absent': Attendance.objects.filter(
            student=student,
            status='absent',
            scan_time__gte=thirty_days_ago
        ).count(),
    }

    # Get available groups (not enrolled in) - filtered by student's gender and education stage
    enrolled_group_ids = active_enrollments.values_list('group_id', flat=True)
    available_groups = Group.objects.filter(
        is_active=True
    ).exclude(
        group_id__in=enrolled_group_ids
    ).select_related('teacher', 'room')

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


@supervisor_required
def student_create(request):
    """
    Create a new student with auto-generated code.
    """
    groups = Group.objects.filter(is_active=True).select_related('teacher', 'room')

    if request.method == 'POST':
        form = StudentForm(request.POST)

        # Get selected groups
        selected_groups = request.POST.getlist('groups')

        if form.is_valid():
            student = form.save()

            # Add to selected groups if any
            for group_id in selected_groups:
                try:
                    group = Group.objects.get(pk=group_id)
                    StudentGroupEnrollment.objects.create(
                        student=student,
                        group=group,
                        financial_status='normal',
                        is_active=True
                    )
                except Group.DoesNotExist:
                    pass

            # Generate barcode image
            try:
                student.save_barcode_image()
            except Exception:
                pass  # Non-critical error

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
        'is_create': True
    })


@supervisor_required
def student_update(request, student_id):
    """
    Update an existing student.
    """
    student = get_object_or_404(Student, pk=student_id)
    groups = Group.objects.filter(is_active=True).select_related('teacher', 'room')

    # Get currently enrolled groups
    current_enrollments = StudentGroupEnrollment.objects.filter(
        student=student,
        is_active=True
    )
    current_group_ids = set(current_enrollments.values_list('group_id', flat=True))

    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)

        # Get selected groups
        selected_groups = request.POST.getlist('groups')
        selected_group_ids = set(int(g) for g in selected_groups if g.isdigit())

        if form.is_valid():
            form.save()

            # Add new enrollments
            for group_id in selected_group_ids - current_group_ids:
                try:
                    group = Group.objects.get(pk=group_id)
                    StudentGroupEnrollment.objects.create(
                        student=student,
                        group=group,
                        financial_status='normal',
                        is_active=True
                    )
                except Group.DoesNotExist:
                    pass

            # Deactivate removed enrollments
            for group_id in current_group_ids - selected_group_ids:
                StudentGroupEnrollment.objects.filter(
                    student=student,
                    group_id=group_id
                ).update(is_active=False)

            messages.success(request, 'تم تحديث بيانات الطالب بنجاح')
            return redirect('students:detail', student_id=student.student_id)
    else:
        form = StudentForm(instance=student)

    return render(request, 'students/form.html', {
        'form': form,
        'student': student,
        'groups': groups,
        'current_group_ids': current_group_ids,
        'is_create': False
    })


@supervisor_required
def student_delete(request, student_id):
    """
    Soft delete a student (set is_active=False).
    """
    student = get_object_or_404(Student, pk=student_id)

    if request.method == 'POST':
        student.is_active = False
        student.save()
        messages.success(request, 'تم حذف الطالب بنجاح')
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
    ).select_related('group', 'group__teacher', 'group__room')[:3]

    # Generate barcode base64 for the card
    barcode_base64 = student.get_barcode_base64()

    context = {
        'student': student,
        'enrollments': active_enrollments,
        'barcode_base64': barcode_base64,
        'today': timezone.now().date(),
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
    ).select_related('group', 'group__teacher', 'group__room')[:3]

    barcode_base64 = student.get_barcode_base64()

    context = {
        'student': student,
        'enrollments': active_enrollments,
        'barcode_base64': barcode_base64,
        'today': timezone.now().date(),
        'print_mode': True
    }

    return render(request, 'students/id_card_print.html', context)


@login_required
def get_next_code(request):
    """
    API endpoint to get next auto-generated student code.
    """
    next_code = Student.generate_next_code()
    return JsonResponse({
        'success': True,
        'next_code': next_code
    })


@login_required
def student_toggle_status(request, student_id):
    """
    Toggle student active status.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'})

    student = get_object_or_404(Student, pk=student_id)
    student.is_active = not student.is_active
    student.save()

    return JsonResponse({
        'success': True,
        'is_active': student.is_active,
        'message': 'تم تحديث الحالة بنجاح'
    })
