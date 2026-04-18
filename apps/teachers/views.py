from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from django.http import JsonResponse
import json

from .models import Teacher, Group, Room, Subject, GroupSchedule
from .forms import TeacherForm, GroupForm, RoomForm, SubjectForm

from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Session, Attendance, ActivityLog


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
    teachers = Teacher.objects.filter(is_active=True).prefetch_related('subjects')
    return render(request, 'teachers/list.html', {'teachers': teachers})


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


@login_required
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
    else:
        form = TeacherForm()
    return render(request, 'teachers/form.html', {'form': form})


@login_required
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
    else:
        form = TeacherForm(instance=teacher)
    return render(request, 'teachers/form.html', {'form': form, 'teacher': teacher})


@login_required
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
    rooms = Room.objects.filter(is_active=True)
    return render(request, 'teachers/rooms/list.html', {'rooms': rooms})


@login_required
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
    else:
        form = RoomForm()
    return render(request, 'teachers/rooms/form.html', {'form': form})


@login_required
def room_detail(request, room_id):
    """
    عرض تفاصيل القاعة مع جدولها وإحصائياتها
    """
    room = get_object_or_404(Room, pk=room_id)
    groups = room.groups.filter(is_active=True).select_related('teacher').annotate(
        students_count=Count(
            'studentgroupenrollment',
            filter=Q(studentgroupenrollment__is_active=True)
        )
    )

    # حساب الطلاب في كل مجموعة
    groups_with_students = []
    total_students = 0

    for group in groups:
        total_students += group.students_count

        groups_with_students.append({
            'group': group,
            'students_count': group.students_count
        })

    # جدول أسبوعي
    from apps.teachers.models import Group
    DAYS = ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    DAYS_AR = {
        'Saturday': 'السبت',
        'Sunday': 'الأحد',
        'Monday': 'الاثنين',
        'Tuesday': 'الثلاثاء',
        'Wednesday': 'الأربعاء',
        'Thursday': 'الخميس',
        'Friday': 'الجمعة'
    }

    weekly_schedule = {}
    for day in DAYS:
        day_groups = groups.filter(schedule_day=day).order_by('schedule_time')
        if day_groups.exists():
            weekly_schedule[day] = {
                'ar_name': DAYS_AR.get(day, day),
                'groups': list(day_groups)
            }

    context = {
        'room': room,
        'groups_with_students': groups_with_students,
        'total_students': total_students,
        'capacity_available': room.capacity - total_students,
        'occupancy_rate': (total_students / room.capacity * 100) if room.capacity > 0 else 0,
        'weekly_schedule': weekly_schedule,
        'DAYS': DAYS
    }

    return render(request, 'teachers/rooms/detail.html', context)


@login_required
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
    else:
        form = RoomForm(instance=room)
    return render(request, 'teachers/rooms/form.html', {'form': form, 'room': room})


@login_required
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
    groups = Group.objects.filter(is_active=True).select_related('teacher', 'room')
    return render(request, 'teachers/groups/list.html', {'groups': groups})


@login_required
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
                ActivityLog.log(
                    user=request.user, action='group_create',
                    description=f'إنشاء مجموعة: {group.group_name}',
                    target_model='Group', target_id=group.pk, request=request
                )
                messages.success(request, 'تم إضافة المجموعة بنجاح')
                return redirect('teachers:group_list')
            except ValidationError as e:
                for field, errs in e.message_dict.items():
                    for err in errs:
                        messages.error(request, err)
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
    group = get_object_or_404(Group, pk=group_id)
    enrolled_students = StudentGroupEnrollment.objects.filter(
        group=group, is_active=True
    ).select_related('student')
    schedules = group.schedules.all().order_by('day_of_week')

    context = {
        'group': group,
        'enrolled_students': enrolled_students,
        'enrolled_count': enrolled_students.count(),
        'capacity': group.room.capacity if group.room else 0,
        'schedules': schedules,
    }
    return render(request, 'teachers/groups/detail.html', context)


@login_required
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
                ActivityLog.log(
                    user=request.user, action='group_update',
                    description=f'تعديل بيانات المجموعة: {group.group_name}',
                    target_model='Group', target_id=group.pk, request=request
                )
                messages.success(request, 'تم تحديث بيانات المجموعة بنجاح')
                return redirect('teachers:group_list')
            except ValidationError as e:
                for field, errs in e.message_dict.items():
                    for err in errs:
                        messages.error(request, err)
    else:
        form = GroupForm(instance=group)

    # Pre-load existing schedules for the template
    existing_schedules = list(group.schedules.values('day_of_week', 'start_time', 'duration'))
    import json
    schedules_json = json.dumps([
        {'day': s['day_of_week'], 'time': s['start_time'].strftime('%H:%M'), 'duration': s['duration']}
        for s in existing_schedules
    ], ensure_ascii=False)

    return render(request, 'teachers/groups/form.html', {
        'form': form,
        'group': group,
        'schedules_json': schedules_json,
    })


@login_required
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


@login_required
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


@login_required
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
    else:
        form = SubjectForm(instance=subject)
    return render(request, 'teachers/subjects/form.html', {
        'form': form,
        'subject': subject,
        'title': f'تعديل المادة: {subject.name}'
    })


@login_required
def subject_delete(request, subject_id):
    """
    حذف المادة الدراسية
    """
    subject = get_object_or_404(Subject, pk=subject_id)
    if request.method == 'POST':
        subject_name = subject.name
        ActivityLog.log(
            user=request.user, action='subject_delete',
            description=f'حذف مادة دراسية: {subject_name}',
            target_model='Subject', target_id=subject.pk, request=request
        )
        subject.delete()
        messages.success(request, f'تم حذف المادة ({subject_name}) بنجاح')
        return redirect('teachers:subject_list')
    return render(request, 'teachers/subjects/confirm_delete.html', {
        'subject': subject
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
        teachers = teachers.filter(subjects__subject_id=subject_id)

    teachers = teachers.distinct()

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


@login_required
def booking_create(request, teacher_id=None):
    """
    إنشاء حجز جديد (مجموعة) وحجز طالب
    """
    teacher = None
    if teacher_id:
        teacher = get_object_or_404(Teacher, pk=teacher_id)

    if request.method == 'POST':
        try:
            data = request.POST

            # Extract form data
            group_name = data.get('group_name')
            subject_id = data.get('subject')
            room_id = data.get('room')
            gender_type = data.get('gender_type')
            education_stage = data.get('education_stage')
            education_year = data.get('education_year')
            duration_minutes = int(data.get('duration_minutes', 120))
            standard_fee = float(data.get('standard_fee', 0))
            center_percentage = float(data.get('center_percentage', 30))

            # Multi-day schedules
            schedules_json = data.get('schedules')
            if schedules_json:
                schedules = json.loads(schedules_json)
            else:
                # Single day fallback
                schedules = [{
                    'day': data.get('schedule_day'),
                    'time': data.get('schedule_time')
                }]

            # Student to enroll
            student_id = data.get('student_id')
            financial_status = data.get('financial_status', 'normal')

            if not schedules:
                messages.error(request, 'يرجى تحديد موعد واحد على الأقل')
                return redirect('teachers:booking_search')

            # Get or create subject
            if subject_id:
                subject = Subject.objects.get(pk=subject_id)
            else:
                subject_name = data.get('subject_name')
                if subject_name:
                    subject, created = Subject.objects.get_or_create(name=subject_name)
                else:
                    messages.error(request, 'يرجى اختيار أو إدخال المادة الدراسية')
                    return redirect('teachers:booking_search')

            # Get room
            room = None
            if room_id:
                room = Room.objects.get(pk=room_id)

            # Create groups for each schedule
            created_groups = []
            for i, schedule in enumerate(schedules):
                group_name_suffix = f" ({schedule['day']})" if len(schedules) > 1 else ""
                final_group_name = f"{group_name}{group_name_suffix}"

                group = Group.objects.create(
                    group_name=final_group_name,
                    teacher=teacher if teacher else Teacher.objects.first(),
                    room=room,
                    subject=subject,
                    schedule_day=schedule['day'],
                    schedule_time=schedule['time'],
                    duration_minutes=duration_minutes,
                    gender_type=gender_type or 'mixed',
                    education_stage=education_stage,
                    education_year=education_year,
                    standard_fee=standard_fee,
                    center_percentage=center_percentage,
                )
                created_groups.append(group)

            # Enroll student if provided
            if student_id:
                student = Student.objects.get(pk=student_id)
                for group in created_groups:
                    StudentGroupEnrollment.objects.get_or_create(
                        student=student,
                        group=group,
                        defaults={
                            'financial_status': financial_status,
                            'is_active': True
                        }
                    )

            messages.success(request, f'تم إنشاء {len(created_groups)} مجموعة بنجاح')
            return redirect('teachers:group_list')

        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
            return redirect('teachers:booking_search')

    # Get data for form
    subjects = Subject.objects.all().order_by('name')
    rooms = Room.objects.filter(is_active=True).order_by('name')
    students = Student.objects.filter(is_active=True).order_by('full_name')

    context = {
        'teacher': teacher,
        'subjects': subjects,
        'rooms': rooms,
        'students': students,
        'week_days': [
            ('Saturday', 'السبت'),
            ('Sunday', 'الأحد'),
            ('Monday', 'الاثنين'),
            ('Tuesday', 'الثلاثاء'),
            ('Wednesday', 'الأربعاء'),
            ('Thursday', 'الخميس'),
            ('Friday', 'الجمعة'),
        ],
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
        'financial_statuses': [
            ('normal', 'عادي'),
            ('symbolic', 'رمزي'),
            ('exempt', 'معفي'),
        ],
    }
    return render(request, 'teachers/bookings/create.html', context)


@login_required
def booking_calendar(request):
    """
    عرض التقويم الشامل لجميع المواعيد
    """
    groups = Group.objects.filter(is_active=True).select_related(
        'teacher', 'room'
    ).order_by('schedule_day', 'schedule_time')

    # Organize by day
    week_days = ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    week_days_arabic = {
        'Saturday': 'السبت',
        'Sunday': 'الأحد',
        'Monday': 'الاثنين',
        'Tuesday': 'الثلاثاء',
        'Wednesday': 'الأربعاء',
        'Thursday': 'الخميس',
        'Friday': 'الجمعة',
    }

    calendar_data = {}
    for day in week_days:
        calendar_data[day] = {
            'arabic_name': week_days_arabic[day],
            'groups': []
        }

    for group in groups:
        day = group.schedule_day
        if day in calendar_data:
            enrolled_count = StudentGroupEnrollment.objects.filter(
                group=group, is_active=True
            ).count()

            calendar_data[day]['groups'].append({
                'id': group.group_id,
                'name': group.group_name,
                'teacher': group.teacher.full_name if group.teacher else '-',
                'subject': group.teacher.get_subjects_display() if group.teacher else '-',
                'room': group.room.name if group.room else '-',
                'time': group.schedule_time.strftime('%I:%M %p'),
                'end_time': group.get_end_time().strftime('%I:%M %p'),
                'duration': group.get_duration_display(),
                'enrolled': enrolled_count,
                'capacity': group.room.capacity if group.room else 0,
                'gender': group.get_gender_type_display(),
                'education_stage': group.get_education_stage_display(),
                'fee': group.standard_fee,
            })

    # Build ordered list of day data for template iteration
    calendar_days = []
    for day in week_days:
        calendar_days.append({
            'name': day,
            'arabic_name': calendar_data[day]['arabic_name'],
            'groups': calendar_data[day]['groups'],
        })

    context = {
        'calendar_data': calendar_data,
        'calendar_days': calendar_days,
        'week_days': week_days,
    }
    return render(request, 'teachers/bookings/calendar.html', context)


@login_required
def booking_student_enroll(request):
    """
    AJAX endpoint لتسجيل طالب في مجموعة موجودة
    """
    if request.method == 'POST':
        import json
        data = json.loads(request.body)

        group_id = data.get('group_id')
        student_id = data.get('student_id')
        financial_status = data.get('financial_status', 'normal')

        try:
            group = Group.objects.get(pk=group_id)
            student = Student.objects.get(pk=student_id)

            # Check if student is already enrolled
            existing = StudentGroupEnrollment.objects.filter(
                student=student, group=group, is_active=True
            ).exists()

            if existing:
                return JsonResponse({'success': False, 'message': 'الطالب مسجل بالفعل في هذه المجموعة'})

            # Enroll student
            enrollment = StudentGroupEnrollment.objects.create(
                student=student,
                group=group,
                financial_status=financial_status,
                is_active=True
            )

            return JsonResponse({
                'success': True,
                'message': 'تم تسجيل الطالب بنجاح'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'طلب غير صحيح'})

