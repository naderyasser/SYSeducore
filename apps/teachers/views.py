from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Teacher, Group, Room, Subject
from .forms import TeacherForm, GroupForm, RoomForm, SubjectForm


# ==================== Teachers ====================

@login_required
def teacher_list(request):
    teachers = Teacher.objects.filter(is_active=True)
    return render(request, 'teachers/list.html', {'teachers': teachers})


@login_required
def teacher_detail(request, teacher_id):
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    groups = teacher.groups.filter(is_active=True)
    return render(request, 'teachers/detail.html', {'teacher': teacher, 'groups': groups})


@login_required
def teacher_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
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
            messages.success(request, 'تم تحديث بيانات المدرس بنجاح')
            return redirect('teachers:detail', teacher_id=teacher_id)
    else:
        form = TeacherForm(instance=teacher)
    return render(request, 'teachers/form.html', {'form': form, 'teacher': teacher})


@login_required
def teacher_delete(request, teacher_id):
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    if request.method == 'POST':
        teacher.is_active = False
        teacher.save()
        messages.success(request, 'تم حذف المدرس بنجاح')
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
            form.save()
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
    groups = room.groups.filter(is_active=True).select_related('teacher')

    # حساب الطلاب في كل مجموعة
    groups_with_students = []
    total_students = 0

    for group in groups:
        from apps.students.models import StudentGroupEnrollment
        students_count = StudentGroupEnrollment.objects.filter(
            group=group,
            is_active=True
        ).count()
        total_students += students_count

        groups_with_students.append({
            'group': group,
            'students_count': students_count
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
            messages.success(request, 'تم تحديث بيانات القاعة بنجاح')
            return redirect('teachers:room_list')
    else:
        form = RoomForm(instance=room)
    return render(request, 'teachers/rooms/form.html', {'form': form, 'room': room})


@login_required
def room_delete(request, room_id):
    room = get_object_or_404(Room, pk=room_id)
    if request.method == 'POST':
        room.is_active = False
        room.save()
        messages.success(request, 'تم حذف القاعة بنجاح')
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
            form.save()
            messages.success(request, 'تم إضافة المجموعة بنجاح')
            return redirect('teachers:group_list')
    else:
        form = GroupForm()
    return render(request, 'teachers/groups/form.html', {'form': form})


@login_required
def group_update(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث بيانات المجموعة بنجاح')
            return redirect('teachers:group_list')
    else:
        form = GroupForm(instance=group)
    return render(request, 'teachers/groups/form.html', {'form': form, 'group': group})


@login_required
def group_delete(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    if request.method == 'POST':
        group.is_active = False
        group.save()
        messages.success(request, 'تم حذف المجموعة بنجاح')
    return redirect('teachers:group_list')


# ==================== Subjects ====================

@login_required
def subject_list(request):
    """
    عرض قائمة المواد الدراسية
    """
    subjects = Subject.objects.all().order_by('name')
    # Count teachers for each subject
    subjects_with_counts = []
    for subject in subjects:
        teachers_count = subject.teachers.count()
        subjects_with_counts.append({
            'subject': subject,
            'teachers_count': teachers_count
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
            form.save()
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
        subject.delete()
        messages.success(request, f'تم حذف المادة ({subject_name}) بنجاح')
        return redirect('teachers:subject_list')
    return render(request, 'teachers/subjects/confirm_delete.html', {
        'subject': subject
    })

