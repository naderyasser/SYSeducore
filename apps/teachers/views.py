from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Teacher, Group, Room
from .forms import TeacherForm, GroupForm, RoomForm


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
        form = TeacherForm(request.POST)
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
        form = TeacherForm(request.POST, instance=teacher)
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
