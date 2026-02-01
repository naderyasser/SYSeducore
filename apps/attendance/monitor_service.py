"""
Live Monitor Service
خدمة الشاشة الحية لمراقبة الحضور

This service provides real-time data aggregation for the live monitoring dashboard
that displays attendance status across all rooms simultaneously.
"""

from datetime import datetime, time, timedelta
from typing import Dict, List, Any, Optional
from django.db.models import Q, Count, Sum, Prefetch
from django.core.cache import cache
from django.utils import timezone
from django.conf import settings


class LiveMonitorService:
    """
    خدمة الشاشة الحية لمراقبة الحضور في جميع القاعات
    Real-time monitoring service for attendance tracking across all rooms
    """
    
    # Cache timeout for live data (5 seconds)
    CACHE_TIMEOUT = 5
    
    # Alert thresholds
    LOW_ATTENDANCE_THRESHOLD = 0.5  # 50%
    HIGH_BLOCKED_THRESHOLD = 3  # More than 3 blocked students
    
    @classmethod
    def get_live_dashboard_data(cls, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get live dashboard data for all rooms
        الحصول على بيانات الشاشة الحية لجميع القاعات
        
        Args:
            use_cache: Whether to use cached data (default: True)
            
        Returns:
            Dict with dashboard data:
            {
                'timestamp': str,
                'summary': {...},
                'rooms': [...],
                'alerts': [...]
            }
        """
        cache_key = f'live_dashboard_data_{timezone.now().strftime("%Y%m%d_%H%M")}'
        
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
        
        # Generate fresh data
        data = cls._generate_dashboard_data()
        
        # Cache for 5 seconds
        cache.set(cache_key, data, cls.CACHE_TIMEOUT)
        
        return data
    
    @classmethod
    def _generate_dashboard_data(cls) -> Dict[str, Any]:
        """Generate fresh dashboard data"""
        from apps.teachers.models import Room, Group
        from apps.attendance.models import Attendance, Session
        from apps.students.models import Student
        
        now = timezone.now()
        current_time = now.time()
        current_day = now.strftime('%A')
        
        # Map English day to Arabic
        day_mapping = {
            'Saturday': 'Saturday',
            'Sunday': 'Sunday',
            'Monday': 'Monday',
            'Tuesday': 'Tuesday',
            'Wednesday': 'Wednesday',
            'Thursday': 'Thursday',
            'Friday': 'Friday'
        }
        
        # Get all active rooms
        rooms = Room.objects.filter(is_active=True).order_by('name')
        
        # Get active sessions for current time
        active_sessions = cls._get_active_sessions(current_day, current_time)
        
        # Build room data
        rooms_data = []
        alerts = []
        total_present_today = 0
        active_session_count = 0
        
        for room in rooms:
            room_data = cls._build_room_data(room, active_sessions, now)
            rooms_data.append(room_data)
            
            if room_data['status'] == 'active':
                active_session_count += 1
                total_present_today += room_data['session']['present']
            
            # Collect alerts
            room_alerts = cls._generate_room_alerts(room_data)
            alerts.extend(room_alerts)
        
        # Build summary
        summary = {
            'total_present_today': total_present_today,
            'active_sessions': active_session_count,
            'total_rooms': rooms.count(),
            'current_time': now.strftime('%H:%M:%S'),
            'current_date': now.strftime('%Y-%m-%d'),
            'current_day_ar': cls._get_arabic_day(current_day)
        }
        
        return {
            'timestamp': now.isoformat(),
            'summary': summary,
            'rooms': rooms_data,
            'alerts': alerts
        }
    
    @classmethod
    def _get_active_sessions(cls, day: str, current_time: time) -> Dict[int, Dict]:
        """
        Get active sessions for current time
        الحصول على الجلسات النشطة للوقت الحالي
        """
        from apps.teachers.models import Group
        
        active_sessions = {}
        
        # Get groups scheduled for today
        groups = Group.objects.filter(
            schedule_day=day,
            is_active=True
        ).select_related('teacher', 'room').prefetch_related(
            'enrolled_students'
        )
        
        for group in groups:
            # Check if session is currently active
            if cls._is_session_active(group.schedule_time, group.session_duration, current_time):
                active_sessions[group.room_id] = {
                    'group': group,
                    'group_name': group.group_name,
                    'teacher_name': group.teacher.full_name,
                    'start_time': group.schedule_time.strftime('%H:%M'),
                    'end_time': group.get_end_time().strftime('%H:%M') if group.get_end_time() else '',
                    'capacity': group.room.capacity if group.room else 0,
                    'group_id': group.group_id
                }
        
        return active_sessions
    
    @classmethod
    def _is_session_active(cls, start_time: time, duration: int, current_time: time) -> bool:
        """
        Check if a session is currently active
        التحقق من أن الجلسة نشطة حالياً
        """
        from datetime import datetime, timedelta
        
        # Convert to datetime for comparison
        start_dt = datetime.combine(datetime.today(), start_time)
        end_dt = start_dt + timedelta(minutes=duration)
        current_dt = datetime.combine(datetime.today(), current_time)
        
        return start_dt <= current_dt <= end_dt
    
    @classmethod
    def _build_room_data(cls, room, active_sessions: Dict, now: datetime) -> Dict[str, Any]:
        """
        Build data for a single room
        بناء بيانات لقاعة واحدة
        """
        from apps.attendance.models import Attendance
        
        # Check if room has active session
        session_info = active_sessions.get(room.room_id)
        
        if session_info:
            # Get attendance data for this session
            group = session_info['group']
            attendance_stats = cls._get_session_attendance_stats(group, now)
            
            # Determine room status
            status = cls._determine_room_status(attendance_stats, room.capacity)
            
            return {
                'id': room.room_id,
                'name': room.name,
                'name_ar': room.name,
                'capacity': room.capacity,
                'status': status,
                'session': {
                    'group_name': session_info['group_name'],
                    'teacher_name': session_info['teacher_name'],
                    'start_time': session_info['start_time'],
                    'end_time': session_info['end_time'],
                    'capacity': session_info['capacity'],
                    **attendance_stats
                }
            }
        else:
            # No active session
            return {
                'id': room.room_id,
                'name': room.name,
                'name_ar': room.name,
                'capacity': room.capacity,
                'status': 'empty',
                'session': None
            }
    
    @classmethod
    def _get_session_attendance_stats(cls, group, now: datetime) -> Dict[str, int]:
        """
        Get attendance statistics for a session
        الحصول على إحصائيات الحضور لجلسة
        """
        from apps.attendance.models import Attendance
        from apps.students.models import StudentGroupEnrollment
        
        # Get enrolled students
        enrollments = StudentGroupEnrollment.objects.filter(
            group=group,
            is_active=True
        ).select_related('student')
        
        total_students = enrollments.count()
        
        # Get today's attendance
        today = now.date()
        attendance_records = Attendance.objects.filter(
            session__date=today,
            student__in=[e.student for e in enrollments]
        )
        
        present = attendance_records.filter(status='present').count()
        late = attendance_records.filter(status='late').count()
        late_blocked = attendance_records.filter(status='late_blocked').count()
        very_late_blocked = attendance_records.filter(status='very_late_blocked').count()
        absent = attendance_records.filter(status='absent').count()
        
        # Calculate not arrived
        not_arrived = total_students - (present + late + late_blocked + very_late_blocked + absent)
        
        return {
            'total': total_students,
            'present': present,
            'late': late,
            'late_blocked': late_blocked,
            'very_late_blocked': very_late_blocked,
            'absent': absent,
            'not_arrived': max(0, not_arrived),
            'blocked_total': late_blocked + very_late_blocked
        }
    
    @classmethod
    def _determine_room_status(cls, stats: Dict, capacity: int) -> str:
        """
        Determine room status based on attendance
        تحديد حالة القاعة بناءً على الحضور
        """
        if stats['total'] == 0:
            return 'empty'
        
        attendance_rate = stats['present'] / stats['total'] if stats['total'] > 0 else 0
        blocked_count = stats['blocked_total']
        
        if blocked_count >= cls.HIGH_BLOCKED_THRESHOLD:
            return 'issues'
        elif attendance_rate < cls.LOW_ATTENDANCE_THRESHOLD:
            return 'low_attendance'
        else:
            return 'active'
    
    @classmethod
    def _generate_room_alerts(cls, room_data: Dict) -> List[Dict[str, Any]]:
        """
        Generate alerts for a room
        إنشاء تنبيهات لقاعة
        """
        alerts = []
        
        if room_data['status'] == 'empty':
            return alerts
        
        session = room_data['session']
        
        # Low attendance alert
        if room_data['status'] == 'low_attendance':
            alerts.append({
                'type': 'low_attendance',
                'severity': 'warning',
                'room': room_data['name'],
                'message': f'حضور منخفض في {room_data["name"]}: {session["present"]}/{session["total"]}',
                'timestamp': timezone.now().strftime('%H:%M')
            })
        
        # High blocked students alert
        if session['blocked_total'] >= cls.HIGH_BLOCKED_THRESHOLD:
            alerts.append({
                'type': 'high_blocked',
                'severity': 'danger',
                'room': room_data['name'],
                'message': f'{session["blocked_total"]} طلاب محظورين في {room_data["name"]}',
                'timestamp': timezone.now().strftime('%H:%M')
            })
        
        # Financial blocks alert
        # This would require additional data from payment system
        
        return alerts
    
    @classmethod
    def _get_arabic_day(cls, day: str) -> str:
        """Get Arabic day name"""
        day_map = {
            'Saturday': 'السبت',
            'Sunday': 'الأحد',
            'Monday': 'الاثنين',
            'Tuesday': 'الثلاثاء',
            'Wednesday': 'الأربعاء',
            'Thursday': 'الخميس',
            'Friday': 'الجمعة'
        }
        return day_map.get(day, day)
    
    @classmethod
    def get_room_detail(cls, room_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed attendance data for a specific room
        الحصول على بيانات حضور مفصلة لقاعة معينة
        """
        from apps.teachers.models import Room, Group
        from apps.attendance.models import Attendance
        from apps.students.models import StudentGroupEnrollment
        
        try:
            room = Room.objects.get(room_id=room_id, is_active=True)
        except Room.DoesNotExist:
            return None
        
        now = timezone.now()
        current_day = now.strftime('%A')
        current_time = now.time()
        
        # Get active session
        active_sessions = cls._get_active_sessions(current_day, current_time)
        session_info = active_sessions.get(room_id)
        
        if not session_info:
            return {
                'room': {
                    'id': room.room_id,
                    'name': room.name,
                    'capacity': room.capacity
                },
                'session': None,
                'students': []
            }
        
        # Get enrolled students with attendance
        enrollments = StudentGroupEnrollment.objects.filter(
            group=session_info['group'],
            is_active=True
        ).select_related('student')
        
        students_data = []
        today = now.date()
        
        for enrollment in enrollments:
            student = enrollment.student
            
            # Get today's attendance
            attendance = Attendance.objects.filter(
                session__date=today,
                student=student
            ).first()
            
            students_data.append({
                'student_id': student.student_id,
                'name': student.full_name,
                'code': student.student_code,
                'status': attendance.status if attendance else 'not_arrived',
                'check_in_time': attendance.check_in_time.strftime('%H:%M:%S') if attendance and attendance.check_in_time else None,
                'is_blocked': enrollment.is_financially_blocked
            })
        
        return {
            'room': {
                'id': room.room_id,
                'name': room.name,
                'capacity': room.capacity
            },
            'session': {
                'group_name': session_info['group_name'],
                'teacher_name': session_info['teacher_name'],
                'start_time': session_info['start_time'],
                'end_time': session_info['end_time']
            },
            'students': students_data
        }
    
    @classmethod
    def get_monitor_settings(cls) -> Dict[str, Any]:
        """
        Get monitor settings from database or defaults
        الحصول على إعدادات الشاشة
        """
        from django.contrib.auth.models import User
        
        # Default settings
        settings = {
            'refresh_interval': 5,  # seconds
            'auto_refresh': True,
            'show_alerts': True,
            'alert_threshold_low_attendance': 50,  # percentage
            'alert_threshold_high_blocked': 3,  # count
            'enable_sound': False,
            'fullscreen_mode': False
        }
        
        # TODO: Load from database settings model if exists
        
        return settings
    
    @classmethod
    def get_printable_report(cls) -> Dict[str, Any]:
        """
        Get data for printable status report
        الحصول على بيانات لتقرير حالة قابل للطباعة
        """
        data = cls.get_live_dashboard_data(use_cache=False)
        
        # Add print-specific formatting
        data['print_timestamp'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        data['generated_by'] = 'نظام الحضور الذكي'
        
        return data
