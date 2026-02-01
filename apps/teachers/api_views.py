"""
API Views for Room Scheduling
واجهات برمجة التطبيقات لنظام جدولة القاعات

This module provides REST API endpoints for:
- Checking room availability
- Getting room schedules
- Room utilization metrics
- Conflict detection
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, time as time_class
from django.core.exceptions import ValidationError
import json
import logging

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def api_available_rooms(request):
    """
    Get available rooms for a given time slot
    البحث عن القاعات المتاحة في وقت معين
    
    Query Parameters:
        day: Day of week (Sunday, Monday, etc.)
        time: Start time in HH:MM format (e.g., "10:00")
        duration: Duration in minutes (default: 120)
        min_capacity: Minimum required capacity (optional)
    
    Returns:
        JSON response with available rooms
    """
    from .services import RoomScheduleService
    
    try:
        day = request.GET.get('day')
        time_str = request.GET.get('time')
        duration = int(request.GET.get('duration', 120))
        min_capacity = request.GET.get('min_capacity')
        
        if not day or not time_str:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters: day and time'
            }, status=400)
        
        # Parse time string
        try:
            hour, minute = map(int, time_str.split(':'))
            start_time = time_class(hour=hour, minute=minute)
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid time format. Use HH:MM'
            }, status=400)
        
        # Get available rooms
        available_rooms = RoomScheduleService.get_available_rooms(
            day=day,
            start_time=start_time,
            duration=duration,
            min_capacity=int(min_capacity) if min_capacity else None
        )
        
        # Format response
        rooms_data = []
        for room_info in available_rooms:
            room = room_info['room']
            rooms_data.append({
                'room_id': room.room_id,
                'name': room.name,
                'capacity': room.capacity,
                'is_available': room_info['is_available'],
                'conflicting_groups': [
                    {
                        'group_id': g.group_id,
                        'name': g.group_name,
                        'time': g.schedule_time.strftime('%H:%M'),
                        'duration': g.session_duration
                    }
                    for g in room_info['conflicting_groups']
                ]
            })
        
        return JsonResponse({
            'success': True,
            'day': day,
            'time': time_str,
            'duration': duration,
            'rooms': rooms_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_room_schedule(request, room_id):
    """
    Get schedule for a specific room
    الحصول على جدول قاعة معينة
    
    Path Parameters:
        room_id: ID of the room
    
    Query Parameters:
        week_start: Start date of the week (optional, format: YYYY-MM-DD)
    
    Returns:
        JSON response with room schedule
    """
    from .services import RoomScheduleService
    
    try:
        room = RoomScheduleService.get_room_by_id(room_id)
        
        if not room:
            return JsonResponse({
                'success': False,
                'error': 'Room not found'
            }, status=404)
        
        # Parse week start date
        week_start_str = request.GET.get('week_start')
        week_start = None
        if week_start_str:
            try:
                week_start = datetime.strptime(week_start_str, '%Y-%m-%d')
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid date format. Use YYYY-MM-DD'
                }, status=400)
        
        schedule = RoomScheduleService.get_room_schedule(room, week_start)
        
        return JsonResponse({
            'success': True,
            'room': {
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity
            },
            'schedule': schedule
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_all_rooms_schedule(request):
    """
    Get schedules for all rooms
    الحصول على جداول جميع القاعات
    
    Query Parameters:
        week_start: Start date of the week (optional)
    
    Returns:
        JSON response with all rooms schedules
    """
    from .services import RoomScheduleService
    
    try:
        # Parse week start date
        week_start_str = request.GET.get('week_start')
        week_start = None
        if week_start_str:
            try:
                week_start = datetime.strptime(week_start_str, '%Y-%m-%d')
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid date format. Use YYYY-MM-DD'
                }, status=400)
        
        schedules = RoomScheduleService.get_all_rooms_schedule(week_start)
        
        return JsonResponse({
            'success': True,
            'schedules': schedules
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_room_utilization(request, room_id):
    """
    Get utilization metrics for a room
    الحصول على إحصائيات استخدام قاعة
    
    Path Parameters:
        room_id: ID of the room
    
    Query Parameters:
        month: Month number (1-12, optional)
        year: Year (optional)
    
    Returns:
        JSON response with utilization metrics
    """
    from .services import RoomScheduleService
    
    try:
        room = RoomScheduleService.get_room_by_id(room_id)
        
        if not room:
            return JsonResponse({
                'success': False,
                'error': 'Room not found'
            }, status=404)
        
        # Parse month and year
        month = request.GET.get('month')
        year = request.GET.get('year')
        
        month = int(month) if month else None
        year = int(year) if year else None
        
        utilization = RoomScheduleService.calculate_room_utilization(
            room, month, year
        )
        
        return JsonResponse({
            'success': True,
            'room': {
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity
            },
            'utilization': utilization
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_all_utilization(request):
    """
    Get utilization metrics for all rooms
    الحصول على إحصائيات استخدام جميع القاعات
    
    Query Parameters:
        month: Month number (1-12, optional)
        year: Year (optional)
    
    Returns:
        JSON response with all rooms utilization
    """
    from .services import RoomScheduleService
    
    try:
        # Parse month and year
        month = request.GET.get('month')
        year = request.GET.get('year')
        
        month = int(month) if month else None
        year = int(year) if year else None
        
        rooms = RoomScheduleService.get_all_active_rooms()
        utilizations = []
        
        for room in rooms:
            util = RoomScheduleService.calculate_room_utilization(
                room, month, year
            )
            utilizations.append({
                'room_id': room.room_id,
                'room_name': room.name,
                'capacity': room.capacity,
                'utilization': util
            })
        
        return JsonResponse({
            'success': True,
            'utilizations': utilizations
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_weekly_grid(request):
    """
    Get weekly schedule grid data
    الحصول على بيانات الشبكة الأسبوعية
    
    Query Parameters:
        start_hour: Start hour (default: 8)
        end_hour: End hour (default: 20)
    
    Returns:
        JSON response with grid data
    """
    from .services import RoomScheduleService
    
    try:
        start_hour = request.GET.get('start_hour')
        end_hour = request.GET.get('end_hour')
        
        start_hour = int(start_hour) if start_hour else None
        end_hour = int(end_hour) if end_hour else None
        
        grid_data = RoomScheduleService.get_weekly_grid_data(start_hour, end_hour)
        
        return JsonResponse({
            'success': True,
            'grid': grid_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_check_conflict(request):
    """
    Check for room scheduling conflict
    فحص وجود تعارض في جدول القاعات
    
    Request Body (JSON):
        room_id: ID of the room
        day: Day of week
        time: Start time in HH:MM format
        duration: Duration in minutes
        exclude_group_id: Group ID to exclude (for updates, optional)
    
    Returns:
        JSON response with conflict details
    """
    from .services import RoomScheduleService
    from .models import Room
    
    try:
        data = json.loads(request.body)
        
        room_id = data.get('room_id')
        day = data.get('day')
        time_str = data.get('time')
        duration = data.get('duration', 120)
        exclude_group_id = data.get('exclude_group_id')
        
        if not room_id or not day or not time_str:
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters: room_id, day, and time'
            }, status=400)
        
        room = Room.objects.filter(room_id=room_id, is_active=True).first()
        if not room:
            return JsonResponse({
                'success': False,
                'error': 'Room not found'
            }, status=404)
        
        # Parse time
        try:
            hour, minute = map(int, time_str.split(':'))
            start_time = time_class(hour=hour, minute=minute)
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid time format. Use HH:MM'
            }, status=400)
        
        # Check conflict
        conflict = RoomScheduleService.check_room_conflict(
            room=room,
            day=day,
            start_time=start_time,
            duration=int(duration),
            exclude_group_id=exclude_group_id
        )
        
        if conflict:
            return JsonResponse({
                'success': True,
                'has_conflict': True,
                'conflict': {
                    'group_name': conflict['conflict_group_name'],
                    'conflict_start': conflict['conflict_start'],
                    'conflict_end': conflict['conflict_end'],
                    'message_ar': conflict['message_ar'],
                    'message_en': conflict['message_en']
                }
            })
        
        return JsonResponse({
            'success': True,
            'has_conflict': False,
            'message': 'No conflict found'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_rooms_list(request):
    """
    Get list of all active rooms
    الحصول على قائمة جميع القاعات النشطة
    
    Returns:
        JSON response with rooms list
    """
    from .services import RoomScheduleService
    
    try:
        rooms = RoomScheduleService.get_all_active_rooms()
        
        rooms_data = [
            {
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity
            }
            for room in rooms
        ]
        
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
@require_http_methods(["GET"])
def api_days_list(request):
    """
    Get list of available days
    الحصول على قائمة الأيام المتاحة
    
    Returns:
        JSON response with days list
    """
    from .models import Group
    
    days = Group.DAYS_CHOICES
    
    days_data = [
        {
            'value': value,
            'label_ar': label,
            'label_en': value
        }
        for value, label in days
    ]
    
    return JsonResponse({
        'success': True,
        'days': days_data
    })
