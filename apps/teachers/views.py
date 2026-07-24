import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import (
    admin_required,
    ajax_supervisor_required,
    supervisor_required,
)

from .models import (
    WEEK_DAYS,
    WEEK_DAYS_AR,
    Group,
    Room,
    Subject,
    Teacher,
    group_schedule_entries,
    room_week_entries,
)
from .forms import TeacherForm, GroupForm, RoomForm, SubjectForm

from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Session, Attendance, ActivityLog

logger = logging.getLogger(__name__)

#: Rows per page on the teacher / room / group list screens.
LIST_PAGE_SIZE = 25

#: Generic message used instead of echoing an exception back to the browser.
GENERIC_ERROR_MESSAGE = 'حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى'


def _paginate(request, queryset, per_page=LIST_PAGE_SIZE):
    """Return the requested page of ``queryset`` (never raises on bad input)."""
    return Paginator(queryset, per_page).get_page(request.GET.get('page'))


def _page_context(page_obj, object_name):
    """Context shared by every paginated list view."""
    return {
        object_name: page_obj,
        'page_obj': page_obj,
        'paginator': page_obj.paginator,
        'is_paginated': page_obj.has_other_pages(),
        'total_count': page_obj.paginator.count,
    }


def _enrollment_count_annotation():
    """Active enrolments per group, as an annotation instead of a query per row."""
    return Count(
        'studentgroupenrollment',
        filter=Q(studentgroupenrollment__is_active=True),
        distinct=True,
    )


def _report_validation_error(request, error):
    """Surface every message of a ``ValidationError`` to the user."""
    error_dict = getattr(error, 'message_dict', None)
    if error_dict:
        for errs in error_dict.values():
            for err in errs:
                messages.error(request, err)
    else:
        for err in getattr(error, 'messages', [str(error)]):
            messages.error(request, err)


def _parse_schedule_data(post_data, default_duration=120):
    """
    Parse schedule data from POST.
    Expects: schedule_days[] with day names, and schedule_time_<DayName> for per-day times.
    Falls back to a single schedule_day + schedule_time if the per-day format is not used.
    """
    from datetime import datetime as dt

    schedule_data = []

    # New format: per-day times
    days = post_data.getlist('schedule_days[]') or post_data.getlist('schedule_days')
    if days:
        for day in days:
            time_str = post_data.get(f'schedule_time_{day}', '').strip()
            duration_str = post_data.get(f'schedule_duration_{day}', '').strip()

            if not time_str:
                # Fall back to default time
                time_str = post_data.get('schedule_time', '').strip()

            if time_str:
                try:
                    parsed_time = dt.strptime(time_str, '%H:%M').time()
                except ValueError:
                    continue

                duration = int(duration_str) if duration_str else default_duration
                schedule_data.append({
                    'day': day,
                    'time': parsed_time,
                    'duration': duration,
                })
    else:
        # Legacy single-day format
        schedule_days_json = post_data.get('schedule_days_json', '')
        if schedule_days_json:
            try:
                parsed = json.loads(schedule_days_json)
                for entry in parsed:
                    time_val = dt.strptime(entry['time'], '%H:%M').time()
                    schedule_data.append({
                        'day': entry['day'],
                        'time': time_val,
                        'duration': int(entry.get('duration', default_duration)),
                    })
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        if not schedule_data:
            day = post_data.get('schedule_day', '').strip()
            time_str = post_data.get('schedule_time', '').strip()
            if day and time_str:
                try:
                    parsed_time = dt.strptime(time_str, '%H:%M').time()
                    schedule_data.append({
                        'day': day,
                        'time': parsed_time,
                        'duration': default_duration,
                    })
                except ValueError:
                    pass

    return schedule_data


# ==================== Teachers ====================

@login_required
def teacher_list(request):
    teachers = (
        Teacher.objects.filter(is_active=True)
        .prefetch_related('subjects')
        .annotate(groups_count=Count('groups', filter=Q(groups__is_active=True), distinct=True))
        .order_by('full_name')
    )
    return render(request, 'teachers/list.html', _page_context(_paginate(request, teachers), 'teachers'))


@login_required
def teacher_detail(request, teacher_id):
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    groups = teacher.groups.filter(is_active=True).annotate(
        students_count=Count(
            'studentgroupenrollment',
            filter=Q(studentgroupenrollment__is_active=True),
        )
    )
    
    # Get upcoming sessions for this teacher (next 7 days)
    today = timezone.now().date()
    next_week = today + timedelta(days=7)
    upcoming_sessions = Session.objects.filter(
        group__teacher=teacher,
        group__is_active=True,  # Filter inactive groups
        session_date__gte=today,
        session_date__lte=next_week,
        is_cancelled=False
    ).select_related('group', 'group__room').order_by('session_date')[:5]
    
    return render(request, 'teachers/detail.html', {
        'teacher': teacher,
        'groups': groups,
        'upcoming_sessions': upcoming_sessions
    })


@supervisor_required
def teacher_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES)
        if form.is_valid():
            teacher = form.save()
            ActivityLog.log(
                user=request.user, action='teacher_create',
                description=f'إضافة مدرس: {teacher.full_name}',
                target_model='Teacher', target_id=teacher.pk, request=request
            )
            messages.success(request, 'تم إضافة المدرس بنجاح')
            return redirect('teachers:list')
        messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = TeacherForm()
    return render(request, 'teachers/form.html', {'form': form})


@supervisor_required
def teacher_update(request, teacher_id):
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES, instance=teacher)
        if form.is_valid():
            form.save()
            ActivityLog.log(
                user=request.user, action='teacher_update',
                description=f'تعديل بيانات المدرس: {teacher.full_name}',
                target_model='Teacher', target_id=teacher.pk, request=request
            )
            messages.success(request, 'تم تحديث بيانات المدرس بنجاح')
            return redirect('teachers:detail', teacher_id=teacher_id)
        # Do not fall through silently: the user must be told the save failed.
        messages.error(request, 'لم يتم حفظ التعديلات — يرجى تصحيح الأخطاء في النموذج')
    else:
        form = TeacherForm(instance=teacher)
    return render(request, 'teachers/form.html', {'form': form, 'teacher': teacher})


@admin_required
def teacher_delete(request, teacher_id):
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    if request.method == 'POST':
        teacher.soft_delete(user=request.user)
        ActivityLog.log(
            user=request.user, action='teacher_delete',
            description=f'حذف مدرس (سلة المهملات): {teacher.full_name}',
            target_model='Teacher', target_id=teacher.pk, request=request
        )
        messages.success(request, f'تم نقل المدرس "{teacher.full_name}" إلى سلة المهملات')
    return redirect('teachers:list')


# ==================== Rooms ====================

@login_required
def room_list(request):
    rooms = (
        Room.objects.filter(is_active=True)
        .annotate(active_groups_count=Count('groups', filter=Q(groups__is_active=True), distinct=True))
        .order_by('name')
    )
    return render(request, 'teachers/rooms/list.html', _page_context(_paginate(request, rooms), 'rooms'))


@supervisor_required
def room_create(request):
    if request.method == 'POST':
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save()
            ActivityLog.log(
                user=request.user, action='room_create',
                description=f'إضافة قاعة: {room.name}',
                target_model='Room', target_id=room.pk, request=request
            )
            messages.success(request, 'تم إضافة القاعة بنجاح')
            return redirect('teachers:room_list')
        messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = RoomForm()
    return render(request, 'teachers/rooms/form.html', {'form': form})


@login_required
def room_detail(request, room_id):
    """
    عرض تفاصيل القاعة مع جدولها وإحصائياتها

    السعة تُقاس لكل حصة على حدة: القاعة التي تستوعب 30 طالباً تستوعب 30 طالباً
    في كل حصة، وليس 30 طالباً موزعين على كل حصص الأسبوع.
    """
    room = get_object_or_404(Room, pk=room_id)
    groups = list(
        room.groups.filter(is_active=True)
        .select_related('teacher', 'room')
        .prefetch_related('schedules')
        .annotate(students_count=_enrollment_count_annotation())
        .order_by('group_name')
    )

    groups_with_students = [
        {'group': group, 'students_count': group.students_count}
        for group in groups
    ]

    # الجدول الأسبوعي — مبني على GroupSchedule (كل أيام المجموعة، وليس اليوم الأول فقط)
    weekly_schedule = {
        day: {'ar_name': WEEK_DAYS_AR.get(day, day), 'groups': entries}
        for day, entries in room_week_entries(room, groups=groups).items()
    }
    sessions_per_week = sum(len(data['groups']) for data in weekly_schedule.values())

    # ذروة الاستخدام = أكبر حصة (لا يجوز جمع كل الحصص معاً)
    peak_students = max((group.students_count for group in groups), default=0)
    distinct_students = (
        StudentGroupEnrollment.objects
        .filter(group__in=groups, is_active=True)
        .values('student').distinct().count()
    ) if groups else 0

    context = {
        'room': room,
        'groups_with_students': groups_with_students,
        # "المستخدم" = أكبر عدد طلاب في حصة واحدة، وهو ما تقيسه سعة القاعة
        'total_students': peak_students,
        'peak_students': peak_students,
        'distinct_students_count': distinct_students,
        'sessions_per_week': sessions_per_week,
        'capacity_available': max(room.capacity - peak_students, 0),
        'occupancy_rate': (peak_students / room.capacity * 100) if room.capacity > 0 else 0,
        'weekly_schedule': weekly_schedule,
        'DAYS': WEEK_DAYS,
    }

    return render(request, 'teachers/rooms/detail.html', context)


@supervisor_required
def room_update(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    if request.method == 'POST':
        form = RoomForm(request.POST, instance=room)
        if form.is_valid():
            form.save()
            ActivityLog.log(
                user=request.user, action='room_update',
                description=f'تعديل بيانات القاعة: {room.name}',
                target_model='Room', target_id=room.pk, request=request
            )
            messages.success(request, 'تم تحديث بيانات القاعة بنجاح')
            return redirect('teachers:room_list')
        # Do not fall through silently: the user must be told the save failed.
        messages.error(request, 'لم يتم حفظ التعديلات — يرجى تصحيح الأخطاء في النموذج')
    else:
        form = RoomForm(instance=room)
    return render(request, 'teachers/rooms/form.html', {'form': form, 'room': room})


@admin_required
def room_delete(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    if request.method == 'POST':
        room.soft_delete(user=request.user)
        ActivityLog.log(
            user=request.user, action='room_delete',
            description=f'حذف قاعة (سلة المهملات): {room.name}',
            target_model='Room', target_id=room.pk, request=request
        )
        messages.success(request, f'تم نقل القاعة "{room.name}" إلى سلة المهملات')
    return redirect('teachers:room_list')


# ==================== Groups ====================

@login_required
def group_list(request):
    groups = (
        Group.objects.filter(is_active=True)
        .select_related('teacher', 'room')
        .prefetch_related('schedules')
        .annotate(students_count=_enrollment_count_annotation())
        .order_by('group_name')
    )
    return render(request, 'teachers/groups/list.html', _page_context(_paginate(request, groups), 'groups'))


@supervisor_required
def group_create(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            # Parse schedule data from POST
            schedule_data = _parse_schedule_data(request.POST, form.cleaned_data.get('duration_minutes', 120))

            if not schedule_data:
                messages.error(request, 'يرجى اختيار يوم واحد على الأقل وتحديد الوقت')
                return render(request, 'teachers/groups/form.html', {'form': form})

            try:
                group = form.save_with_schedules(schedule_data)
            except ValidationError as e:
                _report_validation_error(request, e)
            else:
                ActivityLog.log(
                    user=request.user, action='group_create',
                    description=f'إنشاء مجموعة: {group.group_name}',
                    target_model='Group', target_id=group.pk, request=request
                )
                messages.success(request, 'تم إضافة المجموعة بنجاح')
                return redirect('teachers:group_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = GroupForm()
    return render(request, 'teachers/groups/form.html', {'form': form})


@login_required
def group_detail(request, group_id):
    """
    عرض تفاصيل المجموعة
    """
    group = get_object_or_404(
        Group.objects.select_related('teacher', 'room').prefetch_related('schedules'),
        pk=group_id,
    )
    enrolled_students = StudentGroupEnrollment.objects.filter(
        group=group, is_active=True
    ).select_related('student')
    schedules = group.get_schedules()

    context = {
        'group': group,
        'enrolled_students': enrolled_students,
        'enrolled_count': enrolled_students.count(),
        'capacity': group.room.capacity if group.room else 0,
        'schedules': schedules,
        'schedule_entries': group.get_schedule_entries(),
    }
    return render(request, 'teachers/groups/detail.html', context)


@supervisor_required
def group_update(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            schedule_data = _parse_schedule_data(request.POST, form.cleaned_data.get('duration_minutes', group.duration_minutes))

            if not schedule_data:
                messages.error(request, 'يرجى اختيار يوم واحد على الأقل وتحديد الوقت')
                return render(request, 'teachers/groups/form.html', {'form': form, 'group': group})

            try:
                form.save_with_schedules(schedule_data)
            except ValidationError as e:
                _report_validation_error(request, e)
            else:
                ActivityLog.log(
                    user=request.user, action='group_update',
                    description=f'تعديل بيانات المجموعة: {group.group_name}',
                    target_model='Group', target_id=group.pk, request=request
                )
                messages.success(request, 'تم تحديث بيانات المجموعة بنجاح')
                return redirect('teachers:group_list')
        else:
            # Do not fall through silently: the user must be told the save failed.
            messages.error(request, 'لم يتم حفظ التعديلات — يرجى تصحيح الأخطاء في النموذج')
    else:
        form = GroupForm(instance=group)

    # Pre-load existing schedules for the template
    schedules_json = json.dumps([
        {
            'day': entry.day_of_week,
            'time': entry.start_time.strftime('%H:%M'),
            'duration': entry.duration,
        }
        for entry in group.get_schedule_entries()
    ], ensure_ascii=False)

    return render(request, 'teachers/groups/form.html', {
        'form': form,
        'group': group,
        'schedules_json': schedules_json,
    })


@admin_required
def group_delete(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    if request.method == 'POST':
        group.soft_delete(user=request.user)
        ActivityLog.log(
            user=request.user, action='group_delete',
            description=f'حذف مجموعة (سلة المهملات): {group.group_name}',
            target_model='Group', target_id=group.pk, request=request
        )
        messages.success(request, f'تم نقل المجموعة "{group.group_name}" إلى سلة المهملات')
    return redirect('teachers:group_list')


# ==================== Subjects ====================

@login_required
def subject_list(request):
    """
    عرض قائمة المواد الدراسية
    """
    subjects = Subject.objects.annotate(
        teachers_count_val=Count('teachers')
    ).order_by('name')
    subjects_with_counts = []
    for subject in subjects:
        subjects_with_counts.append({
            'subject': subject,
            'teachers_count': subject.teachers_count_val
        })
    return render(request, 'teachers/subjects/list.html', {
        'subjects_with_counts': subjects_with_counts,
        'total_subjects': subjects.count()
    })


@supervisor_required
def subject_create(request):
    """
    إضافة مادة دراسية جديدة
    """
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save()
            ActivityLog.log(
                user=request.user, action='subject_create',
                description=f'إضافة مادة دراسية: {subject.name}',
                target_model='Subject', target_id=subject.pk, request=request
            )
            messages.success(request, 'تم إضافة المادة الدراسية بنجاح')
            return redirect('teachers:subject_list')
        messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = SubjectForm()
    return render(request, 'teachers/subjects/form.html', {
        'form': form,
        'title': 'إضافة مادة دراسية جديدة'
    })


@login_required
def subject_detail(request, subject_id):
    """
    عرض تفاصيل المادة الدراسية
    """
    subject = get_object_or_404(Subject, pk=subject_id)
    teachers = subject.teachers.filter(is_active=True).order_by('full_name')
    
    return render(request, 'teachers/subjects/detail.html', {
        'subject': subject,
        'teachers': teachers,
        'teachers_count': teachers.count()
    })


@supervisor_required
def subject_update(request, subject_id):
    """
    تعديل بيانات المادة الدراسية
    """
    subject = get_object_or_404(Subject, pk=subject_id)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            ActivityLog.log(
                user=request.user, action='subject_update',
                description=f'تعديل مادة دراسية: {subject.name}',
                target_model='Subject', target_id=subject.pk, request=request
            )
            messages.success(request, 'تم تحديث بيانات المادة الدراسية بنجاح')
            return redirect('teachers:subject_detail', subject_id=subject_id)
        # Do not fall through silently: the user must be told the save failed.
        messages.error(request, 'لم يتم حفظ التعديلات — يرجى تصحيح الأخطاء في النموذج')
    else:
        form = SubjectForm(instance=subject)
    return render(request, 'teachers/subjects/form.html', {
        'form': form,
        'subject': subject,
        'title': f'تعديل المادة: {subject.name}'
    })


@admin_required
def subject_delete(request, subject_id):
    """
    حذف المادة الدراسية (إلى سلة المهملات)

    كان الحذف نهائياً — على عكس كل الكيانات الأخرى — وكان يمسح ارتباط المادة
    بكل المدرسين بلا رجعة. أصبح الآن حذفاً ناعماً يحافظ على الارتباطات،
    مع إظهار عدد المدرسين المتأثرين قبل التأكيد.
    """
    subject = get_object_or_404(Subject, pk=subject_id)
    linked_teachers = list(subject.teachers.filter(is_active=True).order_by('full_name'))

    if request.method == 'POST':
        subject_name = subject.name
        subject.soft_delete(user=request.user)
        ActivityLog.log(
            user=request.user, action='subject_delete',
            description=(
                f'حذف مادة دراسية: {subject_name} '
                f'(مرتبطة بـ {len(linked_teachers)} مدرس)'
            ),
            target_model='Subject', target_id=subject.pk, request=request
        )
        if linked_teachers:
            messages.warning(
                request,
                f'تم نقل المادة ({subject_name}) إلى سلة المهملات — '
                f'كانت مرتبطة بـ {len(linked_teachers)} مدرس'
            )
        else:
            messages.success(request, f'تم نقل المادة ({subject_name}) إلى سلة المهملات')
        return redirect('teachers:subject_list')

    return render(request, 'teachers/subjects/confirm_delete.html', {
        'subject': subject,
        'linked_teachers': linked_teachers,
        'linked_teachers_count': len(linked_teachers),
    })


# ==================== Bookings (المواعيد) ====================

@login_required
def booking_search(request):
    """
    صفحة البحث عن المواعيد - البحث عن المدرسين والمواد والقاعات
    """
    query = request.GET.get('q', '')
    education_stage = request.GET.get('education_stage', '')
    gender = request.GET.get('gender', '')
    subject_id = request.GET.get('subject', '')

    # Get available subjects
    subjects = Subject.objects.all().order_by('name')

    # Base teacher queryset
    teachers = Teacher.objects.filter(is_active=True)

    # Apply filters
    if query:
        teachers = teachers.filter(
            Q(full_name__icontains=query) |
            Q(specialization__icontains=query)
        )

    if education_stage:
        teachers = teachers.filter(groups__education_stage=education_stage)

    if gender:
        teachers = teachers.filter(groups__gender_type=gender)

    if subject_id:
        # ``Subject``'s primary key is ``id`` — ``subjects__subject_id`` was a
        # FieldError, i.e. a 500 as soon as the subject filter was used.
        teachers = teachers.filter(subjects__pk=subject_id)

    teachers = teachers.distinct().prefetch_related('subjects')

    # Get available rooms
    rooms = Room.objects.filter(is_active=True).order_by('name')

    # Get upcoming sessions (next 7 days)
    today = timezone.now().date()
    next_week = today + timedelta(days=7)
    upcoming_sessions = Session.objects.filter(
        session_date__gte=today,
        session_date__lte=next_week,
        is_cancelled=False,
        group__is_active=True  # Filter inactive groups
    ).select_related('group', 'group__teacher', 'group__room').order_by('session_date')

    # Get recent attendance stats (last 7 days)
    last_week = today - timedelta(days=7)
    attendance_stats = Attendance.objects.filter(
        session__session_date__gte=last_week,
        session__session_date__lte=today
    ).aggregate(
        total=Count('attendance_id'),
        present=Count('attendance_id', filter=Q(status='present')),
        late=Count('attendance_id', filter=Q(status='late')),
        absent=Count('attendance_id', filter=Q(status='absent'))
    )

    context = {
        'teachers': teachers,
        'subjects': subjects,
        'rooms': rooms,
        'query': query,
        'education_stage': education_stage,
        'gender': gender,
        'selected_subject': subject_id,
        'education_stages': [
            ('primary', 'ابتدائي'),
            ('preparatory', 'اعدادي'),
            ('secondary', 'ثانوي'),
        ],
        'gender_types': [
            ('male', 'بنين'),
            ('female', 'بنات'),
            ('mixed', 'مختلط'),
        ],
        'upcoming_sessions': upcoming_sessions,
        'attendance_stats': attendance_stats,
    }
    return render(request, 'teachers/bookings/search.html', context)


def _booking_create_context(teacher, form_data=None):
    """Context for the booking form (also used to re-render it after an error)."""
    return {
        'teacher': teacher,
        'teachers': Teacher.objects.filter(is_active=True).order_by('full_name'),
        'subjects': Subject.objects.all().order_by('name'),
        'rooms': Room.objects.filter(is_active=True).order_by('name'),
        'students': Student.objects.filter(is_active=True).order_by('full_name'),
        'submitted': form_data or {},
        'week_days': [(day, WEEK_DAYS_AR[day]) for day in WEEK_DAYS],
        'education_stages': [
            ('primary', 'ابتدائي'),
            ('preparatory', 'اعدادي'),
            ('secondary', 'ثانوي'),
        ],
        'education_years': [
            ('1', 'الصف الأول'),
            ('2', 'الصف الثاني'),
            ('3', 'الصف الثالث'),
            ('4', 'الصف الرابع'),
            ('5', 'الصف الخامس'),
            ('6', 'الصف السادس'),
        ],
        'gender_types': [
            ('male', 'بنين'),
            ('female', 'بنات'),
            ('mixed', 'مختلط'),
        ],
        'financial_statuses': list(StudentGroupEnrollment.FINANCIAL_STATUS_CHOICES),
    }


def _parse_booking_schedules(data, default_duration):
    """
    Normalise the booking form's schedule payload into the shape
    ``GroupForm.save_with_schedules`` expects.

    Accepts the page's ``schedules`` JSON field (``[{"day": ..., "time": "HH:MM"}]``)
    and falls back to a single ``schedule_day`` / ``schedule_time`` pair.
    Raises ``ValueError`` with an Arabic message on malformed input.
    """
    from datetime import datetime as dt

    raw = data.get('schedules')
    if raw:
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError('صيغة المواعيد غير صحيحة')
    else:
        entries = [{'day': data.get('schedule_day'), 'time': data.get('schedule_time')}]

    valid_days = {day for day, _ in Group.DAYS_CHOICES}
    schedule_data = []
    seen_days = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('صيغة المواعيد غير صحيحة')
        day = (entry.get('day') or '').strip()
        time_str = (entry.get('time') or '').strip()
        if not day or not time_str:
            continue
        if day not in valid_days:
            raise ValueError(f'يوم غير صحيح: {day}')
        if day in seen_days:
            raise ValueError(f'تم تحديد يوم {WEEK_DAYS_AR.get(day, day)} أكثر من مرة')
        try:
            parsed_time = dt.strptime(time_str, '%H:%M').time()
        except ValueError:
            raise ValueError(f'صيغة الوقت غير صحيحة: {time_str}')
        seen_days.add(day)
        schedule_data.append({
            'day': day,
            'time': parsed_time,
            'duration': int(entry.get('duration') or default_duration),
        })

    return schedule_data


@supervisor_required
def booking_create(request, teacher_id=None):
    """
    إنشاء حجز جديد (مجموعة بمواعيدها) وتسجيل طالب

    The old implementation passed ``subject=`` to ``Group.objects.create()``.
    ``Group`` has no ``subject`` field — subjects belong to the *teacher*
    (``Teacher.subjects``) — so every single submission raised ``TypeError``,
    which a bare ``except Exception`` turned into "حدث خطأ". It also created one
    ``Group`` per day and silently fell back to ``Teacher.objects.first()`` when
    no teacher had been chosen.

    Now: one group with one ``GroupSchedule`` row per selected day, the teacher
    is mandatory, the chosen subject is attached to the teacher, and validation
    errors are shown on the form instead of being swallowed.
    """
    teacher = None
    if teacher_id:
        teacher = get_object_or_404(Teacher, pk=teacher_id)

    if request.method != 'POST':
        return render(request, 'teachers/bookings/create.html', _booking_create_context(teacher))

    data = request.POST

    def fail(message):
        messages.error(request, message)
        return render(
            request, 'teachers/bookings/create.html',
            _booking_create_context(teacher, form_data=data),
        )

    # --- teacher (mandatory) ------------------------------------------------
    if teacher is None:
        posted_teacher = (data.get('teacher') or data.get('teacher_id') or '').strip()
        if not posted_teacher:
            return fail('يرجى اختيار المدرس')
        teacher = Teacher.objects.filter(pk=posted_teacher, is_active=True).first()
        if teacher is None:
            return fail('المدرس المحدد غير موجود')

    # --- schedules ----------------------------------------------------------
    try:
        duration_minutes = int(data.get('duration_minutes') or 120)
    except (TypeError, ValueError):
        return fail('مدة الحصة غير صحيحة')

    try:
        schedule_data = _parse_booking_schedules(data, duration_minutes)
    except ValueError as exc:
        return fail(str(exc))

    if not schedule_data:
        return fail('يرجى تحديد موعد واحد على الأقل')

    # --- subject ------------------------------------------------------------
    education_stage = (data.get('education_stage') or '').strip()
    subject_pk = (data.get('subject') or '').strip()
    subject_name = (data.get('subject_name') or '').strip()

    if subject_pk:
        subject = Subject.objects.filter(pk=subject_pk).first()
        if subject is None:
            return fail('المادة الدراسية المحددة غير موجودة')
    elif subject_name:
        # ``Subject`` is unique on ``(name, education_stage)`` — looking it up by
        # name alone raised ``MultipleObjectsReturned`` for a name taught in more
        # than one stage. ``all_objects`` so a soft-deleted subject is revived
        # instead of colliding with the unique index.
        subject, _created = Subject.all_objects.get_or_create(
            name=subject_name,
            education_stage=education_stage if education_stage in dict(Subject.EDUCATION_STAGE_CHOICES) else '',
        )
        if subject.deleted_at is not None:
            subject.restore()
    else:
        return fail('يرجى اختيار أو إدخال المادة الدراسية')

    # --- student (optional) -------------------------------------------------
    student = None
    student_id = (data.get('student_id') or '').strip()
    if student_id:
        student = Student.objects.filter(pk=student_id).first()
        if student is None:
            return fail('الطالب المحدد غير موجود')

    financial_status = data.get('financial_status') or 'normal'
    if financial_status not in dict(StudentGroupEnrollment.FINANCIAL_STATUS_CHOICES):
        return fail('الحالة المالية غير صحيحة')

    # --- build the group through GroupForm so every validator runs ----------
    form = GroupForm({
        'group_name': (data.get('group_name') or '').strip(),
        'teacher': teacher.pk,
        'room': (data.get('room') or '').strip(),
        'duration_minutes': duration_minutes,
        'gender_type': data.get('gender_type') or 'mixed',
        'education_stage': education_stage,
        'education_year': (data.get('education_year') or '').strip(),
        'standard_fee': data.get('standard_fee') or '0',
        'center_percentage': data.get('center_percentage') or '30',
        'sessions_per_month': data.get('sessions_per_month') or 4,
        'is_active': True,
    })

    if not form.is_valid():
        for errs in form.errors.values():
            for err in errs:
                messages.error(request, err)
        return render(
            request, 'teachers/bookings/create.html',
            _booking_create_context(teacher, form_data=data),
        )

    try:
        with transaction.atomic():
            group = form.save_with_schedules(schedule_data)
            teacher.subjects.add(subject)
            if student is not None:
                enrollment, created = StudentGroupEnrollment.objects.get_or_create(
                    student=student,
                    group=group,
                    defaults={'financial_status': financial_status, 'is_active': True},
                )
                if not created and not enrollment.is_active:
                    enrollment.is_active = True
                    enrollment.financial_status = financial_status
                    enrollment.save(update_fields=['is_active', 'financial_status'])
    except ValidationError as exc:
        _report_validation_error(request, exc)
        return render(
            request, 'teachers/bookings/create.html',
            _booking_create_context(teacher, form_data=data),
        )

    ActivityLog.log(
        user=request.user, action='group_create',
        description=f'إنشاء حجز/مجموعة: {group.group_name} ({len(schedule_data)} موعد)',
        target_model='Group', target_id=group.pk, request=request,
    )
    if student is not None:
        ActivityLog.log(
            user=request.user, action='enrollment_create',
            description=f'تسجيل الطالب {student.full_name} في المجموعة {group.group_name}',
            target_model='StudentGroupEnrollment', target_id=group.pk, request=request,
        )

    messages.success(
        request,
        f'تم إنشاء المجموعة "{group.group_name}" بنجاح مع {len(schedule_data)} موعد'
    )
    return redirect('teachers:group_detail', group_id=group.pk)


@login_required
def booking_calendar(request):
    """
    عرض التقويم الشامل لجميع المواعيد

    التقويم مبني على ``GroupSchedule``: المجموعة التي تجتمع ثلاثة أيام تظهر
    في الأيام الثلاثة، لا في اليوم الأول فقط.
    """
    groups = (
        Group.objects.filter(is_active=True)
        .select_related('teacher', 'room')
        .prefetch_related('schedules', 'teacher__subjects')
        .annotate(enrolled_count=_enrollment_count_annotation())
    )

    calendar_data = {
        day: {'arabic_name': WEEK_DAYS_AR[day], 'groups': []}
        for day in WEEK_DAYS
    }

    for group in groups:
        for entry in group_schedule_entries(group):
            day_bucket = calendar_data.get(entry.day_of_week)
            if day_bucket is None:
                continue
            day_bucket['groups'].append({
                'id': group.group_id,
                'name': group.group_name,
                'teacher': group.teacher.full_name if group.teacher else '-',
                'subject': group.teacher.get_subjects_display() if group.teacher else '-',
                'room': group.room.name if group.room else '-',
                'time': entry.start_time.strftime('%I:%M %p'),
                'end_time': entry.get_end_time().strftime('%I:%M %p'),
                'duration': entry.get_duration_display(),
                'enrolled': group.enrolled_count,
                'capacity': group.room.capacity if group.room else 0,
                'gender': group.get_gender_type_display(),
                'education_stage': group.get_education_stage_display(),
                'fee': group.standard_fee,
                'start_time': entry.start_time,
            })

    for day_bucket in calendar_data.values():
        day_bucket['groups'].sort(key=lambda item: item['start_time'])

    # Build ordered list of day data for template iteration
    calendar_days = [
        {
            'name': day,
            'arabic_name': calendar_data[day]['arabic_name'],
            'groups': calendar_data[day]['groups'],
        }
        for day in WEEK_DAYS
    ]

    context = {
        'calendar_data': calendar_data,
        'calendar_days': calendar_days,
        'week_days': WEEK_DAYS,
    }
    return render(request, 'teachers/bookings/calendar.html', context)


@ajax_supervisor_required
def booking_student_enroll(request):
    """
    AJAX endpoint لتسجيل طالب في مجموعة موجودة
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طلب غير صحيح'}, status=405)

    try:
        data = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'message': 'صيغة الطلب غير صحيحة'}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({'success': False, 'message': 'صيغة الطلب غير صحيحة'}, status=400)

    group_id = data.get('group_id')
    student_id = data.get('student_id')
    financial_status = data.get('financial_status') or 'normal'

    if financial_status not in dict(StudentGroupEnrollment.FINANCIAL_STATUS_CHOICES):
        return JsonResponse({'success': False, 'message': 'الحالة المالية غير صحيحة'}, status=400)

    group = Group.objects.filter(pk=group_id).first()
    if group is None:
        return JsonResponse({'success': False, 'message': 'المجموعة غير موجودة'}, status=404)

    student = Student.objects.filter(pk=student_id).first()
    if student is None:
        return JsonResponse({'success': False, 'message': 'الطالب غير موجود'}, status=404)

    try:
        with transaction.atomic():
            enrollment, created = StudentGroupEnrollment.objects.get_or_create(
                student=student,
                group=group,
                defaults={'financial_status': financial_status, 'is_active': True},
            )
            if not created:
                if enrollment.is_active:
                    return JsonResponse({
                        'success': False,
                        'message': 'الطالب مسجل بالفعل في هذه المجموعة',
                    }, status=400)
                # Re-enrolling someone previously removed: ``get_or_create``
                # ignores ``defaults`` for an existing row, so activate it here.
                enrollment.is_active = True
                enrollment.financial_status = financial_status
                enrollment.save(update_fields=['is_active', 'financial_status'])
    except Exception:
        # Never echo the exception text back to the browser (it leaks model
        # names, SQL fragments and file paths); log it instead.
        logger.exception('booking_student_enroll failed (group=%s student=%s)', group_id, student_id)
        return JsonResponse({'success': False, 'message': GENERIC_ERROR_MESSAGE}, status=500)

    ActivityLog.log(
        user=request.user, action='enrollment_create',
        description=f'تسجيل الطالب {student.full_name} في المجموعة {group.group_name}',
        target_model='StudentGroupEnrollment', target_id=enrollment.pk, request=request,
    )

    return JsonResponse({'success': True, 'message': 'تم تسجيل الطالب بنجاح'})

