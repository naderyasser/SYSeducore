"""
Room APIs for the booking screens.

Two things every view here has in common:

* **Capacity is per session.** A room that seats 30 seats 30 students *in each
  session*, not 30 spread over the whole week. Summing enrolments across every
  group in a room reported a room used by five groups as 5× over capacity.
* **``GroupSchedule`` is the source of truth for the timetable.** A group may
  meet on several days with a different time each day; the legacy
  ``Group.schedule_day``/``schedule_time`` columns only ever describe the first.
"""
import json
import logging
from datetime import datetime

from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import ajax_login_required
from apps.students.models import StudentGroupEnrollment

from .models import (
    WEEK_DAYS,
    WEEK_DAYS_AR,
    Group,
    GroupSchedule,
    Room,
    find_room_conflicts,
    room_schedule_entries,
    room_week_entries,
)

logger = logging.getLogger(__name__)

#: Returned instead of ``str(exception)`` — raw exception text leaks model
#: names, SQL fragments and file paths to the browser.
GENERIC_ERROR_MESSAGE = 'حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى'


def _server_error(context, exc):
    logger.exception('%s failed: %s', context, exc)
    return JsonResponse({'success': False, 'error': GENERIC_ERROR_MESSAGE}, status=500)


def _active_groups(room):
    """Active groups with at least one session in ``room``, enrolment count annotated."""
    return list(
        Group.objects.filter(schedules__room=room, is_active=True, deleted_at__isnull=True)
        .select_related('teacher')
        .prefetch_related('schedules__room')
        .distinct()
        .annotate(
            students_count=Count(
                'studentgroupenrollment',
                filter=Q(studentgroupenrollment__is_active=True),
                distinct=True,
            )
        )
        .order_by('group_name')
    )


def _peak_usage(groups):
    """Largest single session in the room — what its capacity actually limits."""
    return max((group.students_count for group in groups), default=0)


def _occupancy(peak, capacity):
    return round((peak / capacity * 100) if capacity > 0 else 0, 1)


@ajax_login_required
def room_list_api(request):
    """
    API Endpoint: قائمة بجميع القاعات مع معلومات إضافية
    """
    try:
        rooms = Room.objects.filter(is_active=True).order_by('name')

        rooms_data = []
        for room in rooms:
            groups = _active_groups(room)
            peak = _peak_usage(groups)
            students_by_group = {g.group_id: g.students_count for g in groups}

            groups_list = []
            for entry in room_schedule_entries(room):
                students_count = students_by_group.get(entry.group_id, 0)
                groups_list.append({
                    'id': entry.group_id,
                    'name': entry.group_name,
                    'teacher': entry.teacher.full_name if entry.teacher else '-',
                    'day': entry.get_day_display(),
                    'time': entry.start_time.strftime('%I:%M %p'),
                    'students_count': students_count,
                    'is_full': students_count >= room.capacity,
                })

            rooms_data.append({
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity,
                # per-session usage, not the sum across the week
                'capacity_used': peak,
                'capacity_available': max(room.capacity - peak, 0),
                'occupancy_rate': _occupancy(peak, room.capacity),
                'groups_count': len(groups),
                'sessions_per_week': len(groups_list),
                'is_active': room.is_active,
                'groups': groups_list,
            })

        return JsonResponse({'success': True, 'rooms': rooms_data})

    except Exception as exc:
        return _server_error('room_list_api', exc)


@ajax_login_required
def room_detail_api(request, room_id):
    """
    API Endpoint: تفاصيل قاعة محددة مع جدولها الكامل
    """
    try:
        room = Room.objects.filter(pk=room_id, is_active=True).first()
        if room is None:
            return JsonResponse({'success': False, 'error': 'القاعة غير موجودة'}, status=404)

        groups = _active_groups(room)
        peak = _peak_usage(groups)
        students_by_group = {g.group_id: g.students_count for g in groups}

        schedule = {}
        sessions_per_week = 0
        for day, entries in room_week_entries(room).items():
            sessions_per_week += len(entries)
            schedule[day] = [
                {
                    'id': entry.group_id,
                    'name': entry.group_name,
                    'teacher': entry.teacher.full_name if entry.teacher else '-',
                    'time': entry.start_time.strftime('%I:%M %p'),
                    'time_end': entry.get_end_time().strftime('%I:%M %p'),
                    'duration': entry.get_duration_display(),
                    'students_count': students_by_group.get(entry.group_id, 0),
                    'fee': float(entry.group.standard_fee),
                    'is_full': students_by_group.get(entry.group_id, 0) >= room.capacity,
                }
                for entry in entries
            ]

        return JsonResponse({
            'success': True,
            'room': {
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity,
                'capacity_used': peak,
                'capacity_available': max(room.capacity - peak, 0),
                'occupancy_rate': _occupancy(peak, room.capacity),
                'groups_count': len(groups),
                'sessions_per_week': sessions_per_week,
                'is_active': room.is_active,
            },
            'schedule': schedule,
            'groups': [
                {
                    'id': group.group_id,
                    'name': group.group_name,
                    'teacher': group.teacher.full_name if group.teacher else '-',
                    'day': group.get_schedule_day_display(),
                    'time': group.schedule_time.strftime('%I:%M %p') if group.schedule_time else '',
                    'schedule': [
                        {
                            'day': entry.get_day_display(),
                            'time': entry.start_time.strftime('%I:%M %p'),
                            'time_end': entry.get_end_time().strftime('%I:%M %p'),
                        }
                        for entry in group.get_schedule_entries()
                    ],
                }
                for group in groups
            ],
        })

    except Exception as exc:
        return _server_error('room_detail_api', exc)


@ajax_login_required
@require_http_methods(["POST"])
def room_availability_check(request):
    """
    API Endpoint: التحقق من توفر القاعة في وقت معين
    """
    try:
        try:
            data = json.loads(request.body or b'{}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'success': False, 'error': 'صيغة الطلب غير صحيحة'}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({'success': False, 'error': 'صيغة الطلب غير صحيحة'}, status=400)

        room_id = data.get('room_id')
        day = data.get('day')  # Monday, Tuesday, etc.
        time = data.get('time')  # HH:MM format

        if not all([room_id, day, time]):
            return JsonResponse({'success': False, 'error': 'جميع الحقول مطلوبة'}, status=400)

        if day not in WEEK_DAYS:
            return JsonResponse({'success': False, 'error': 'اليوم غير صحيح'}, status=400)

        try:
            room = Room.objects.filter(pk=int(room_id), is_active=True).first()
        except (TypeError, ValueError):
            room = None
        if room is None:
            return JsonResponse({'success': False, 'error': 'القاعة غير موجودة'}, status=404)

        try:
            schedule_time = datetime.strptime(time, '%H:%M').time()
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'صيغة الوقت غير صحيحة'}, status=400)

        try:
            duration = int(data.get('duration_minutes') or 120)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'مدة الحصة غير صحيحة'}, status=400)
        if duration < 1:
            return JsonResponse({'success': False, 'error': 'مدة الحصة غير صحيحة'}, status=400)

        raw_exclude_group_pk = data.get('exclude_group_id') or None
        exclude_group_pk = None
        if raw_exclude_group_pk is not None:
            try:
                exclude_group_pk = int(raw_exclude_group_pk)
            except (TypeError, ValueError):
                return JsonResponse({'success': False, 'error': 'معرف المجموعة غير صحيح'}, status=400)

        # Smart overlap check against every scheduled session in the room —
        # including days 2..n of multi-day groups.
        conflicting = find_room_conflicts(
            room, day, schedule_time, duration, exclude_group_pk=exclude_group_pk
        )

        if conflicting:
            return JsonResponse({
                'success': True,
                'available': False,
                'message': 'القاعة محجوزة - يوجد تداخل في التوقيت',
                'conflicts': [
                    {
                        'id': entry.group_id,
                        'name': entry.group_name,
                        'teacher': entry.teacher.full_name if entry.teacher else '-',
                        'day': entry.get_day_display(),
                        'time_start': entry.start_time.strftime('%I:%M %p'),
                        'time_end': entry.get_end_time().strftime('%I:%M %p'),
                        'duration': entry.get_duration_display(),
                    }
                    for entry in conflicting
                ],
            })

        return JsonResponse({
            'success': True,
            'available': True,
            'message': 'القاعة متاحة في هذا التوقيت',
        })

    except Exception as exc:
        return _server_error('room_availability_check', exc)


@ajax_login_required
def room_statistics_api(request):
    """
    API Endpoint: إحصائيات القاعات

    Two queries in total: the rooms, plus one grouped count of active enrolments
    per group. The previous implementation walked every room three times and ran
    a ``COUNT`` per group (~3 × rooms × groups queries).
    """
    try:
        rooms = list(
            Room.objects.filter(is_active=True)
            .annotate(
                active_groups_count=Count(
                    'schedule_entries__group',
                    filter=Q(
                        schedule_entries__group__is_active=True,
                        schedule_entries__group__deleted_at__isnull=True,
                    ),
                    distinct=True,
                )
            )
            .order_by('name')
        )

        # Largest single session per room — capacity is per session. One
        # grouped query for every group in the system, folded in Python.
        peak_by_room = {}
        group_counts = (
            GroupSchedule.objects.filter(
                room__isnull=False,
                group__is_active=True,
                group__deleted_at__isnull=True,
            )
            .values('room_id', 'group_id')
            .annotate(
                students=Count(
                    'group__studentgroupenrollment',
                    filter=Q(group__studentgroupenrollment__is_active=True),
                    distinct=True,
                )
            )
            .values_list('room_id', 'group_id', 'students')
        )
        for room_pk, _group_pk, students in group_counts:
            if students > peak_by_room.get(room_pk, 0):
                peak_by_room[room_pk] = students

        total_rooms = len(rooms)
        total_capacity = sum(room.capacity for room in rooms)
        total_capacity_used = 0
        active_groups_count = 0
        full_rooms = []
        empty_rooms = []

        for room in rooms:
            peak = peak_by_room.get(room.pk, 0)
            total_capacity_used += peak
            active_groups_count += room.active_groups_count

            if room.active_groups_count == 0:
                empty_rooms.append({
                    'id': room.room_id,
                    'name': room.name,
                    'capacity': room.capacity,
                })
            elif peak >= room.capacity:
                full_rooms.append({
                    'id': room.room_id,
                    'name': room.name,
                    'capacity': room.capacity,
                    'used': peak,
                })

        return JsonResponse({
            'success': True,
            'statistics': {
                'total_rooms': total_rooms,
                'total_capacity': total_capacity,
                'total_capacity_used': total_capacity_used,
                'total_capacity_available': max(total_capacity - total_capacity_used, 0),
                'occupancy_rate': _occupancy(total_capacity_used, total_capacity),
                'active_groups_count': active_groups_count,
                'full_rooms_count': len(full_rooms),
                'empty_rooms_count': len(empty_rooms),
            },
            'full_rooms': full_rooms,
            'empty_rooms': empty_rooms,
        })

    except Exception as exc:
        return _server_error('room_statistics_api', exc)


@ajax_login_required
def room_schedule_api(request, room_id):
    """
    API Endpoint: جدول قاعة محددة لهذا الأسبوع
    """
    try:
        room = Room.objects.filter(pk=room_id, is_active=True).first()
        if room is None:
            return JsonResponse({'success': False, 'error': 'القاعة غير موجودة'}, status=404)

        groups = _active_groups(room)

        # One query for every enrolled student in the room instead of one per group.
        students_by_group = {}
        enrollments = (
            StudentGroupEnrollment.objects
            .filter(group__in=groups, is_active=True)
            .select_related('student')
        )
        for enrollment in enrollments:
            students_by_group.setdefault(enrollment.group_id, []).append({
                'id': enrollment.student.student_id,
                'name': enrollment.student.full_name,
                'code': enrollment.student.student_code,
                'financial_status': enrollment.get_financial_status_display(),
            })

        schedule_data = {}
        for day, entries in room_week_entries(room).items():
            schedule_data[day] = {
                'ar_name': WEEK_DAYS_AR.get(day, day),
                'sessions': [
                    {
                        'id': entry.group_id,
                        'name': entry.group_name,
                        'teacher': entry.teacher.full_name if entry.teacher else '-',
                        'time': entry.start_time.strftime('%I:%M %p'),
                        'time_end': entry.get_end_time().strftime('%I:%M %p'),
                        'students_count': len(students_by_group.get(entry.group_id, [])),
                        'students': students_by_group.get(entry.group_id, []),
                    }
                    for entry in entries
                ],
            }

        return JsonResponse({
            'success': True,
            'room': {
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity,
            },
            'schedule': schedule_data,
        })

    except Exception as exc:
        return _server_error('room_schedule_api', exc)
