from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
import json

from .models import Room, Group, Teacher
from apps.students.models import Student, StudentGroupEnrollment


@login_required
def room_list_api(request):
    """
    API Endpoint: قائمة بجميع القاعات مع معلومات إضافية
    """
    try:
        rooms = Room.objects.filter(is_active=True).annotate(
            groups_count=Count('groups', filter=Q(groups__is_active=True))
        ).prefetch_related('groups__teacher')

        rooms_data = []
        for room in rooms:
            # جلب المجموعات النشطة في القاعة
            active_groups = room.groups.filter(is_active=True)

            # حساب السعة المستخدمة
            total_capacity_used = 0
            groups_list = []

            for group in active_groups:
                # عدد الطلاب المسجلين في المجموعة
                students_count = StudentGroupEnrollment.objects.filter(
                    group=group,
                    is_active=True
                ).count()

                total_capacity_used += students_count

                groups_list.append({
                    'id': group.group_id,
                    'name': group.group_name,
                    'teacher': group.teacher.full_name if group.teacher else '-',
                    'day': group.get_schedule_day_display(),
                    'time': group.schedule_time.strftime('%I:%M %p'),
                    'students_count': students_count,
                    'is_full': students_count >= room.capacity
                })

            # حساب نسبة الامتلاء
            occupancy_rate = (total_capacity_used / room.capacity * 100) if room.capacity > 0 else 0

            rooms_data.append({
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity,
                'capacity_used': total_capacity_used,
                'capacity_available': room.capacity - total_capacity_used,
                'occupancy_rate': round(occupancy_rate, 1),
                'groups_count': active_groups.count(),
                'is_active': room.is_active,
                'groups': groups_list
            })

        return JsonResponse({
            'success': True,
            'rooms': rooms_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def room_detail_api(request, room_id):
    """
    API Endpoint: تفاصيل قاعة محددة مع جدولها الكامل
    """
    try:
        room = Room.objects.get(pk=room_id, is_active=True)

        # جلب المجموعات النشطة
        active_groups = room.groups.filter(is_active=True).select_related('teacher')

        # جلب الجدول الأسبوعي للقاعة
        DAYS = ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        schedule = {}

        for day in DAYS:
            day_groups = active_groups.filter(schedule_day=day)
            if day_groups.exists():
                schedule[day] = []
                for group in day_groups.order_by('schedule_time'):
                    students_count = StudentGroupEnrollment.objects.filter(
                        group=group,
                        is_active=True
                    ).count()

                    schedule[day].append({
                        'id': group.group_id,
                        'name': group.group_name,
                        'teacher': group.teacher.full_name if group.teacher else '-',
                        'time': group.schedule_time.strftime('%I:%M %p'),
                        'time_end': group.get_end_time().strftime('%I:%M %p'),
                        'duration': group.get_duration_display(),
                        'students_count': students_count,
                        'fee': float(group.standard_fee),
                        'is_full': students_count >= room.capacity
                    })

        # حساب إحصائيات القاعة
        total_students = 0
        for group in active_groups:
            total_students += StudentGroupEnrollment.objects.filter(
                group=group,
                is_active=True
            ).count()

        # الحصص في الأسبوع
        sessions_per_week = active_groups.count()

        return JsonResponse({
            'success': True,
            'room': {
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity,
                'capacity_used': total_students,
                'capacity_available': room.capacity - total_students,
                'occupancy_rate': round((total_students / room.capacity * 100) if room.capacity > 0 else 0, 1),
                'groups_count': active_groups.count(),
                'sessions_per_week': sessions_per_week,
                'is_active': room.is_active
            },
            'schedule': schedule,
            'groups': [
                {
                    'id': g.group_id,
                    'name': g.group_name,
                    'teacher': g.teacher.full_name if g.teacher else '-',
                    'day': g.get_schedule_day_display(),
                    'time': g.schedule_time.strftime('%I:%M %p')
                }
                for g in active_groups
            ]
        })

    except Room.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'القاعة غير موجودة'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def room_availability_check(request):
    """
    API Endpoint: التحقق من توفر القاعة في وقت معين
    """
    try:
        data = json.loads(request.body)
        room_id = data.get('room_id')
        day = data.get('day')  # Monday, Tuesday, etc.
        time = data.get('time')  # HH:MM format

        if not all([room_id, day, time]):
            return JsonResponse({
                'success': False,
                'error': 'جميع الحقول مطلوبة'
            }, status=400)

        room = Room.objects.get(pk=room_id, is_active=True)

        # تحويل الوقت
        try:
            schedule_time = datetime.strptime(time, '%H:%M').time()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'صيغة الوقت غير صحيحة'
            }, status=400)

        # البحث عن مجموعات متداخلة في التوقيت (Smart Overlap Check)
        schedule_time_dt = datetime.combine(datetime.today(), schedule_time)
        duration = int(data.get('duration_minutes', 120))
        new_end_dt = schedule_time_dt + timedelta(minutes=duration)

        other_groups = Group.objects.filter(
            room=room,
            schedule_day=day,
            is_active=True
        )

        conflicting_groups = []
        for other in other_groups:
            other_start = datetime.combine(datetime.today(), other.schedule_time)
            other_end = other_start + timedelta(minutes=other.duration_minutes)

            # Check overlap: start1 < end2 AND start2 < end1
            if schedule_time_dt < other_end and other_start < new_end_dt:
                conflicting_groups.append(other)

        if conflicting_groups:
            conflicts = []
            for group in conflicting_groups:
                conflicts.append({
                    'id': group.group_id,
                    'name': group.group_name,
                    'teacher': group.teacher.full_name if group.teacher else '-',
                    'time_start': group.schedule_time.strftime('%I:%M %p'),
                    'time_end': group.get_end_time().strftime('%I:%M %p'),
                    'duration': group.get_duration_display(),
                })

            return JsonResponse({
                'success': True,
                'available': False,
                'message': 'القاعة محجوزة - يوجد تداخل في التوقيت',
                'conflicts': conflicts
            })

        return JsonResponse({
            'success': True,
            'available': True,
            'message': 'القاعة متاحة في هذا التوقيت'
        })

    except Room.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'القاعة غير موجودة'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def room_statistics_api(request):
    """
    API Endpoint: إحصائيات القاعات
    """
    try:
        rooms = Room.objects.filter(is_active=True)

        total_rooms = rooms.count()
        total_capacity = sum(r.capacity for r in rooms)

        # حساب السعة المستخدمة
        total_capacity_used = 0
        active_groups_count = 0

        for room in rooms:
            active_groups = room.groups.filter(is_active=True)
            active_groups_count += active_groups.count()

            for group in active_groups:
                students_count = StudentGroupEnrollment.objects.filter(
                    group=group,
                    is_active=True
                ).count()
                total_capacity_used += students_count

        # القاعات الكاملة
        full_rooms = []
        for room in rooms:
            room_used = 0
            for group in room.groups.filter(is_active=True):
                room_used += StudentGroupEnrollment.objects.filter(
                    group=group,
                    is_active=True
                ).count()

            if room_used >= room.capacity:
                full_rooms.append({
                    'id': room.room_id,
                    'name': room.name,
                    'capacity': room.capacity,
                    'used': room_used
                })

        # القاعات الفارغة
        empty_rooms = []
        for room in rooms:
            if not room.groups.filter(is_active=True).exists():
                empty_rooms.append({
                    'id': room.room_id,
                    'name': room.name,
                    'capacity': room.capacity
                })

        return JsonResponse({
            'success': True,
            'statistics': {
                'total_rooms': total_rooms,
                'total_capacity': total_capacity,
                'total_capacity_used': total_capacity_used,
                'total_capacity_available': total_capacity - total_capacity_used,
                'occupancy_rate': round((total_capacity_used / total_capacity * 100) if total_capacity > 0 else 0, 1),
                'active_groups_count': active_groups_count,
                'full_rooms_count': len(full_rooms),
                'empty_rooms_count': len(empty_rooms)
            },
            'full_rooms': full_rooms,
            'empty_rooms': empty_rooms
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def room_schedule_api(request, room_id):
    """
    API Endpoint: جدول قاعة محددة لهذا الأسبوع
    """
    try:
        room = Room.objects.get(pk=room_id, is_active=True)

        # جلب جميع المجموعات في القاعة
        groups = room.groups.filter(is_active=True).select_related('teacher').prefetch_related(
            'enrolled_students__student'
        )

        schedule_data = {}

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

        for day in DAYS:
            day_groups = groups.filter(schedule_day=day).order_by('schedule_time')
            if day_groups.exists():
                schedule_data[day] = {
                    'ar_name': DAYS_AR.get(day, day),
                    'sessions': []
                }

                for group in day_groups:
                    # جلب الطلاب المسجلين
                    enrolled_students = StudentGroupEnrollment.objects.filter(
                        group=group,
                        is_active=True
                    ).select_related('student')

                    students_list = []
                    for enrollment in enrolled_students:
                        students_list.append({
                            'id': enrollment.student.student_id,
                            'name': enrollment.student.full_name,
                            'code': enrollment.student.student_code,
                            'financial_status': enrollment.get_financial_status_display()
                        })

                    schedule_data[day]['sessions'].append({
                        'id': group.group_id,
                        'name': group.group_name,
                        'teacher': group.teacher.full_name if group.teacher else '-',
                        'time': group.schedule_time.strftime('%I:%M %p'),
                        'students_count': len(students_list),
                        'students': students_list
                    })

        return JsonResponse({
            'success': True,
            'room': {
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity
            },
            'schedule': schedule_data
        })

    except Room.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'القاعة غير موجودة'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
