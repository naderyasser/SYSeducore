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


# ==================== Room Scheduling Dashboard ====================

@login_required
def room_schedule_dashboard(request):
    """
    Room availability dashboard with weekly grid view
    لوحة معلومات توفر القاعات مع عرض الشبكة الأسبوعية
    """
    from .services import RoomScheduleService
    
    # Get filter parameters
    selected_day = request.GET.get('day', '')
    selected_time = request.GET.get('time', '')
    start_hour = int(request.GET.get('start_hour', 8))
    end_hour = int(request.GET.get('end_hour', 20))
    
    # Get grid data
    grid_data = RoomScheduleService.get_weekly_grid_data(start_hour, end_hour)
    
    # Get all rooms with utilization
    rooms = Room.objects.filter(is_active=True)
    rooms_with_utilization = []
    
    for room in rooms:
        utilization = RoomScheduleService.calculate_room_utilization(room)
        rooms_with_utilization.append({
            'room': room,
            'utilization': utilization
        })
    
    # Sort by utilization (highest first)
    rooms_with_utilization.sort(key=lambda x: x['utilization']['utilization_percentage'], reverse=True)
    
    context = {
        'grid_data': grid_data,
        'rooms_with_utilization': rooms_with_utilization,
        'selected_day': selected_day,
        'selected_time': selected_time,
        'start_hour': start_hour,
        'end_hour': end_hour,
        'days': Group.DAYS_CHOICES,
    }
    
    return render(request, 'teachers/rooms/schedule_dashboard.html', context)


@login_required
def room_detail_schedule(request, room_id):
    """
    Detailed schedule view for a specific room
    عرض جدول مفصل لقاعة معينة
    """
    from .services import RoomScheduleService
    
    room = get_object_or_404(Room, pk=room_id)
    
    # Get schedule
    schedule = RoomScheduleService.get_room_schedule(room)
    
    # Get utilization
    utilization = RoomScheduleService.calculate_room_utilization(room)
    
    context = {
        'room': room,
        'schedule': schedule,
        'utilization': utilization,
        'days': Group.DAYS_CHOICES,
    }
    
    return render(request, 'teachers/rooms/detail_schedule.html', context)


@login_required
def find_available_room(request):
    """
    Find available rooms for a given time slot
    البحث عن قاعات متاحة لوقت معين
    """
    from .services import RoomScheduleService
    from datetime import time as time_class
    
    available_rooms = None
    selected_day = request.GET.get('day', '')
    selected_time = request.GET.get('time', '')
    min_capacity = request.GET.get('min_capacity', '')
    duration = int(request.GET.get('duration', 120))
    
    if selected_day and selected_time:
        try:
            hour, minute = map(int, selected_time.split(':'))
            start_time = time_class(hour=hour, minute=minute)
            
            available_rooms = RoomScheduleService.get_available_rooms(
                day=selected_day,
                start_time=start_time,
                duration=duration,
                min_capacity=int(min_capacity) if min_capacity else None
            )
        except (ValueError, IndexError):
            pass
    
    context = {
        'available_rooms': available_rooms,
        'selected_day': selected_day,
        'selected_time': selected_time,
        'min_capacity': min_capacity,
        'duration': duration,
        'days': Group.DAYS_CHOICES,
        'durations': Group.DURATION_CHOICES,
    }
    
    return render(request, 'teachers/rooms/find_available.html', context)


@login_required
def room_utilization_report(request):
    """
    Room utilization report with metrics
    تقرير إحصائيات استخدام القاعات
    """
    from .services import RoomScheduleService
    
    # Get filter parameters
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    month = int(month) if month else None
    year = int(year) if year else None
    
    # Get all rooms with utilization
    rooms = Room.objects.filter(is_active=True)
    rooms_with_utilization = []
    
    total_utilization = 0
    peak_hours_global = {}
    
    for room in rooms:
        utilization = RoomScheduleService.calculate_room_utilization(room, month, year)
        rooms_with_utilization.append({
            'room': room,
            'utilization': utilization
        })
        
        total_utilization += utilization['utilization_percentage']
        
        # Aggregate peak hours
        for hour, count in utilization['hour_distribution'].items():
            peak_hours_global[hour] = peak_hours_global.get(hour, 0) + count
    
    # Calculate average utilization
    avg_utilization = total_utilization / len(rooms) if rooms else 0
    
    # Find global peak hours
    if peak_hours_global:
        max_count = max(peak_hours_global.values())
        global_peak_hours = [h for h, c in peak_hours_global.items() if c == max_count]
    else:
        global_peak_hours = []
    
    # Sort by utilization
    rooms_with_utilization.sort(key=lambda x: x['utilization']['utilization_percentage'], reverse=True)
    
    context = {
        'rooms_with_utilization': rooms_with_utilization,
        'avg_utilization': round(avg_utilization, 2),
        'global_peak_hours': global_peak_hours,
        'selected_month': month,
        'selected_year': year,
        'months': list(range(1, 13)),
        'years': list(range(2023, 2031)),
    }
    
    return render(request, 'teachers/rooms/utilization_report.html', context)
