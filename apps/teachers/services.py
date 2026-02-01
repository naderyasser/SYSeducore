"""
Room Schedule Service
خدمة جدولة القاعات - للكشف عن التعارضات وإدارة الحجوزات

This service provides intelligent room scheduling with:
- Conflict detection for overlapping time ranges
- Available room finding
- Room utilization metrics
- Schedule visualization
"""

from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Any
from django.db import models
from django.db.models import Q, Count
from django.utils import timezone
from django.core.cache import cache


class RoomScheduleService:
    """
    خدمة متقدمة لإدارة جداول القاعات
    Advanced room scheduling service with conflict detection
    """
    
    # الفاصل الزمني الإلزامي بين الحصص (بالدقائق)
    BUFFER_MINUTES = 15
    
    # ساعات العمل الافتراضية
    WORK_HOUR_START = 8  # 8:00 AM
    WORK_HOUR_END = 20   # 8:00 PM
    
    @classmethod
    def check_room_conflict(
        cls,
        room,
        day: str,
        start_time: time,
        duration: int,
        exclude_group_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        فحص وجود تعارض في حجز القاعة
        Check if a room has a scheduling conflict
        
        Args:
            room: Room instance
            day: Day of week (e.g., 'Sunday', 'Monday')
            start_time: Start time (datetime.time object)
            duration: Session duration in minutes
            exclude_group_id: Group ID to exclude from check (for updates)
            
        Returns:
            None if no conflict, dict with conflict details if conflict exists:
            {
                'conflicting_group': Group instance,
                'message_ar': 'Arabic error message',
                'message_en': 'English error message'
            }
        """
        from .models import Group
        
        # حساب وقت الانتهاء مع الفاصل الزمني
        end_time = cls._calculate_end_time(start_time, duration)
        
        # البحث عن المجموعات في نفس القاعة واليوم
        queryset = Group.objects.filter(
            room=room,
            schedule_day=day,
            is_active=True
        )
        
        # استبعاد المجموعة الحالية عند التعديل
        if exclude_group_id:
            queryset = queryset.exclude(group_id=exclude_group_id)
        
        # فحص كل مجموعة للكشف عن التعارض الزمني
        for group in queryset:
            group_end = group.get_end_time()
            
            if not group_end:
                continue
            
            # حساب وقت بدء ونهاية كل مجموعة مع الفاصل الزمني
            group_start_with_buffer = cls._subtract_minutes(group.schedule_time, cls.BUFFER_MINUTES)
            group_end_with_buffer = cls._add_minutes(group_end, cls.BUFFER_MINUTES)
            
            # فحص التداخل الزمني
            if cls._times_overlap(
                start_time, end_time,
                group_start_with_buffer, group_end_with_buffer
            ):
                return {
                    'conflicting_group': group,
                    'message_ar': (
                        f'⛔ تعارض في الجدول: القاعة "{room.name}" محجوزة لمجموعة "{group.group_name}" '
                        f'من {group.schedule_time.strftime("%H:%M")} إلى {group_end.strftime("%H:%M")}. '
                        f'يجب وجود فاصل {cls.BUFFER_MINUTES} دقيقة على الأقل بين الحصص.'
                    ),
                    'message_en': (
                        f'Schedule conflict: Room "{room.name}" is booked by group "{group.group_name}" '
                        f'from {group.schedule_time.strftime("%H:%M")} to {group_end.strftime("%H:%M")}. '
                        f'A {cls.BUFFER_MINUTES}-minute buffer is required between sessions.'
                    ),
                    'conflict_start': group.schedule_time.strftime("%H:%M"),
                    'conflict_end': group_end.strftime("%H:%M"),
                    'conflict_group_name': group.group_name
                }
        
        return None
    
    @classmethod
    def get_available_rooms(
        cls,
        day: str,
        start_time: time,
        duration: int,
        min_capacity: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        البحث عن القاعات المتاحة في وقت معين
        Find available rooms for a given time slot
        
        Args:
            day: Day of week
            start_time: Start time
            duration: Duration in minutes
            min_capacity: Minimum required capacity (optional)
            
        Returns:
            List of available rooms with details:
            [
                {
                    'room': Room instance,
                    'capacity': int,
                    'is_available': bool,
                    'conflicting_groups': [Group instances]
                }
            ]
        """
        from .models import Room, Group
        
        # الحصول على جميع القاعات النشطة
        rooms = Room.objects.filter(is_active=True)
        
        if min_capacity:
            rooms = rooms.filter(capacity__gte=min_capacity)
        
        available_rooms = []
        
        for room in rooms:
            conflict = cls.check_room_conflict(room, day, start_time, duration)
            conflicting_groups = []
            
            if conflict:
                # البحث عن جميع المجموعات المتعارضة
                end_time = cls._calculate_end_time(start_time, duration)
                groups = Group.objects.filter(
                    room=room,
                    schedule_day=day,
                    is_active=True
                )
                
                for group in groups:
                    group_end = group.get_end_time()
                    if group_end:
                        group_start_with_buffer = cls._subtract_minutes(
                            group.schedule_time, cls.BUFFER_MINUTES
                        )
                        group_end_with_buffer = cls._add_minutes(
                            group_end, cls.BUFFER_MINUTES
                        )
                        
                        if cls._times_overlap(
                            start_time, end_time,
                            group_start_with_buffer, group_end_with_buffer
                        ):
                            conflicting_groups.append(group)
            
            available_rooms.append({
                'room': room,
                'capacity': room.capacity,
                'is_available': conflict is None,
                'conflicting_groups': conflicting_groups
            })
        
        # ترتيب: المتاحة أولاً، ثم حسب السعة
        available_rooms.sort(key=lambda x: (not x['is_available'], -x['capacity']))
        
        return available_rooms
    
    @classmethod
    def get_room_schedule(
        cls,
        room,
        week_start_date: Optional[datetime] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        الحصول على جدول أسبوعي للقاعة
        Get weekly schedule for a room
        
        Args:
            room: Room instance
            week_start_date: Start of week (defaults to current week)
            
        Returns:
            Dict with days as keys and list of sessions:
            {
                'Sunday': [
                    {
                        'group': Group instance,
                        'start': '10:00',
                        'end': '12:00',
                        'teacher': 'Teacher Name'
                    }
                ],
                ...
            }
        """
        from .models import Group
        
        if not week_start_date:
            week_start_date = timezone.now()
        
        days = ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        schedule = {day: [] for day in days}
        
        groups = Group.objects.filter(
            room=room,
            is_active=True
        ).order_by('schedule_day', 'schedule_time')
        
        for group in groups:
            end_time = group.get_end_time()
            schedule[group.schedule_day].append({
                'group': group,
                'group_id': group.group_id,
                'group_name': group.group_name,
                'start': group.schedule_time.strftime('%H:%M'),
                'end': end_time.strftime('%H:%M') if end_time else None,
                'teacher': group.teacher.full_name,
                'duration': group.session_duration
            })
        
        return schedule
    
    @classmethod
    def get_all_rooms_schedule(
        cls,
        week_start_date: Optional[datetime] = None
    ) -> Dict[str, Dict[str, List[Dict]]]:
        """
        الحصول على جداول جميع القاعات
        Get schedules for all rooms
        
        Returns:
            Dict with room names as keys:
            {
                'Room 1': {
                    'Sunday': [...],
                    'Monday': [...]
                }
            }
        """
        from .models import Room
        
        rooms = Room.objects.filter(is_active=True)
        all_schedules = {}
        
        for room in rooms:
            all_schedules[room.name] = {
                'room_id': room.room_id,
                'capacity': room.capacity,
                'schedule': cls.get_room_schedule(room, week_start_date)
            }
        
        return all_schedules
    
    @classmethod
    def calculate_room_utilization(
        cls,
        room,
        month: Optional[int] = None,
        year: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        حساب نسبة استخدام القاعة
        Calculate room utilization percentage
        
        Args:
            room: Room instance
            month: Month (1-12), defaults to current month
            year: Year, defaults to current year
            
        Returns:
            Dict with utilization metrics:
            {
                'utilization_percentage': float,
                'total_hours': float,
                'available_hours': float,
                'used_hours': float,
                'session_count': int,
                'peak_hours': List[str],
                'underutilized': bool
            }
        """
        from .models import Group
        
        if not month:
            month = timezone.now().month
        if not year:
            year = timezone.now().year
        
        # حساب عدد الأسابيع في الشهر
        import calendar
        first_day = datetime(year, month, 1)
        last_day = datetime(year, month, calendar.monthrange(year, month)[1])
        weeks_in_month = (last_day - first_day).days / 7
        
        # حساب الساعات المتاحة (8 ساعات يومياً × 7 أيام × عدد الأسابيع)
        daily_hours = cls.WORK_HOUR_END - cls.WORK_HOUR_START
        available_hours = daily_hours * 7 * weeks_in_month
        
        # الحصول على جميع المجموعات النشطة في القاعة
        groups = Group.objects.filter(
            room=room,
            is_active=True
        )
        
        used_hours = 0
        session_count = groups.count()
        hour_distribution = {hour: 0 for hour in range(cls.WORK_HOUR_START, cls.WORK_HOUR_END)}
        
        for group in groups:
            duration_hours = group.session_duration / 60
            used_hours += duration_hours
            
            # تسجيل التوزيع الزمني
            start_hour = group.schedule_time.hour
            for h in range(start_hour, min(start_hour + int(duration_hours), cls.WORK_HOUR_END)):
                if h in hour_distribution:
                    hour_distribution[h] += 1
        
        # حساب نسبة الاستخدام
        utilization_percentage = (used_hours / available_hours * 100) if available_hours > 0 else 0
        
        # تحديد ساعات الذروة
        peak_hours = [
            f"{hour:02d}:00" 
            for hour, count in hour_distribution.items() 
            if count == max(hour_distribution.values())
        ]
        
        # تحديد ما إذا كانت القاعة غير مستغلة بشكل جيد
        underutilized = utilization_percentage < 50
        
        return {
            'utilization_percentage': round(utilization_percentage, 2),
            'total_hours': round(available_hours, 2),
            'used_hours': round(used_hours, 2),
            'available_hours': round(available_hours - used_hours, 2),
            'session_count': session_count,
            'peak_hours': peak_hours,
            'hour_distribution': hour_distribution,
            'underutilized': underutilized
        }
    
    @classmethod
    def get_weekly_grid_data(
        cls,
        start_hour: int = None,
        end_hour: int = None
    ) -> Dict[str, Any]:
        """
        بيانات شبكة الجدول الأسبوعي للعرض المرئي
        Get data for weekly schedule grid visualization
        
        Args:
            start_hour: Start hour (default: 8)
            end_hour: End hour (default: 20)
            
        Returns:
            Dict with grid data:
            {
                'rooms': [...],
                'time_slots': [...],
                'days': [...],
                'schedule': {...}
            }
        """
        from .models import Room
        
        if start_hour is None:
            start_hour = cls.WORK_HOUR_START
        if end_hour is None:
            end_hour = cls.WORK_HOUR_END
        
        rooms = list(Room.objects.filter(is_active=True).order_by('name'))
        days = ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        time_slots = [f"{h:02d}:00" for h in range(start_hour, end_hour + 1)]
        
        # بناء الشبكة
        schedule = {}
        for room in rooms:
            schedule[room.name] = {}
            for day in days:
                schedule[room.name][day] = {}
                for slot in time_slots:
                    schedule[room.name][day][slot] = {
                        'available': True,
                        'group': None
                    }
        
        # تعبئة الحجوزات
        from .models import Group
        groups = Group.objects.filter(is_active=True)
        
        for group in groups:
            end_time = group.get_end_time()
            if not end_time:
                continue
            
            start_hour_group = group.schedule_time.hour
            end_hour_group = end_time.hour
            
            for hour in range(start_hour_group, end_hour_group + 1):
                slot = f"{hour:02d}:00"
                if slot in time_slots and group.room:
                    if group.room.name in schedule:
                        if group.schedule_day in schedule[group.room.name]:
                            if slot in schedule[group.room.name][group.schedule_day]:
                                schedule[group.room.name][group.schedule_day][slot] = {
                                    'available': False,
                                    'group': {
                                        'id': group.group_id,
                                        'name': group.group_name,
                                        'teacher': group.teacher.full_name,
                                        'start': group.schedule_time.strftime('%H:%M'),
                                        'end': end_time.strftime('%H:%M')
                                    }
                                }
        
        return {
            'rooms': [{'id': r.room_id, 'name': r.name, 'capacity': r.capacity} for r in rooms],
            'time_slots': time_slots,
            'days': days,
            'schedule': schedule
        }
    
    @classmethod
    def _calculate_end_time(cls, start_time: time, duration: int) -> time:
        """
        حساب وقت الانتهاء
        Calculate end time from start time and duration
        """
        start_datetime = datetime.combine(datetime.today(), start_time)
        end_datetime = start_datetime + timedelta(minutes=duration)
        return end_datetime.time()
    
    @classmethod
    def _add_minutes(cls, time_obj: time, minutes: int) -> time:
        """
        إضافة دقائق للوقت
        Add minutes to a time object
        """
        dt = datetime.combine(datetime.today(), time_obj) + timedelta(minutes=minutes)
        return dt.time()
    
    @classmethod
    def _subtract_minutes(cls, time_obj: time, minutes: int) -> time:
        """
        طرح دقائق من الوقت
        Subtract minutes from a time object
        """
        dt = datetime.combine(datetime.today(), time_obj) - timedelta(minutes=minutes)
        return dt.time()
    
    @classmethod
    def _times_overlap(
        cls,
        start1: time, end1: time,
        start2: time, end2: time
    ) -> bool:
        """
        فحص تداخل نطاقين زمنيين
        Check if two time ranges overlap
        """
        # تحويل الأوقات إلى دقائق للمقارنة
        start1_min = start1.hour * 60 + start1.minute
        end1_min = end1.hour * 60 + end1.minute
        start2_min = start2.hour * 60 + start2.minute
        end2_min = end2.hour * 60 + end2.minute
        
        # فحص التداخل
        return not (end1_min <= start2_min or start1_min >= end2_min)
    
    @classmethod
    def get_room_by_id(cls, room_id: int):
        """
        الحصول على القاعة بالمعرف
        Get room by ID
        """
        from .models import Room
        return Room.objects.filter(room_id=room_id, is_active=True).first()
    
    @classmethod
    def get_all_active_rooms(cls) -> List:
        """
        الحصول على جميع القاعات النشطة
        Get all active rooms
        """
        from .models import Room
        return list(Room.objects.filter(is_active=True).order_by('name'))
