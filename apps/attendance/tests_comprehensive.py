"""
Comprehensive Unit Tests for Attendance App
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, time, timedelta
from apps.accounts.models import User
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room
from apps.attendance.models import Session, Attendance, BlockedAttempt
from apps.attendance.services import AttendanceService


class AttendanceServiceTestCase(TestCase):
    """Test AttendanceService"""
    
    def setUp(self):
        # Create test data
        self.supervisor = User.objects.create_user(
            username='supervisor',
            password='SecurePass123!',
            role='supervisor'
        )
        
        self.teacher = Teacher.objects.create(
            teacher_name='Test Teacher',
            phone='+201234567890',
            is_active=True
        )
        
        self.room = Room.objects.create(
            room_name='Room 101',
            capacity=30,
            is_active=True
        )
        
        # Create group with schedule for today
        current_day = timezone.now().strftime('%A')
        current_time = timezone.now().time()
        
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day=current_day,
            schedule_time=current_time.replace(minute=0, second=0),
            session_price=100.00,
            is_active=True
        )
        
        self.student = Student.objects.create(
            full_name='Test Student',
            student_code='TEST001',
            parent_phone='+201234567890',
            is_active=True
        )
        
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            is_active=True
        )
        
        # Create today's session
        self.session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date(),
            session_time=self.group.schedule_time,
            status='scheduled'
        )
    
    def test_get_current_day_name(self):
        """Test get_current_day_name method"""
        day_name = AttendanceService.get_current_day_name()
        self.assertIn(day_name, ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
    
    def test_process_scan_invalid_code(self):
        """Test process_scan with invalid student code"""
        result = AttendanceService.process_scan(
            student_code='INVALID',
            supervisor=self.supervisor
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'blocked_other')
        self.assertFalse(result['allow_entry'])
    
    def test_process_scan_inactive_student(self):
        """Test process_scan with inactive student"""
        self.student.is_active = False
        self.student.save()
        
        result = AttendanceService.process_scan(
            student_code='TEST001',
            supervisor=self.supervisor
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'blocked_other')
    
    def test_process_scan_no_session(self):
        """Test process_scan with no matching session"""
        # Delete the session
        self.session.delete()
        
        result = AttendanceService.process_scan(
            student_code='TEST001',
            supervisor=self.supervisor
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'no_session')
        self.assertFalse(result['allow_entry'])


class SessionModelTestCase(TestCase):
    """Test Session model"""
    
    def setUp(self):
        self.teacher = Teacher.objects.create(
            teacher_name='Test Teacher',
            is_active=True
        )
        
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_price=100.00,
            is_active=True
        )
    
    def test_session_creation(self):
        """Test session is created correctly"""
        session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date(),
            session_time=time(10, 0),
            status='scheduled'
        )
        self.assertEqual(session.status, 'scheduled')
        self.assertFalse(session.teacher_attended)
        self.assertIsNone(session.teacher_checkin_time)
    
    def test_session_string_representation(self):
        """Test __str__ method"""
        session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date(),
            session_time=time(10, 0)
        )
        expected = f"{self.group.group_name} - {session.session_date}"
        self.assertEqual(str(session), expected)


class AttendanceModelTestCase(TestCase):
    """Test Attendance model"""
    
    def setUp(self):
        self.teacher = Teacher.objects.create(
            teacher_name='Test Teacher',
            is_active=True
        )
        
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_price=100.00,
            is_active=True
        )
        
        self.session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date(),
            session_time=time(10, 0)
        )
        
        self.student = Student.objects.create(
            full_name='Test Student',
            student_code='TEST001',
            is_active=True
        )
    
    def test_attendance_creation(self):
        """Test attendance record creation"""
        attendance = Attendance.objects.create(
            session=self.session,
            student=self.student,
            status='present',
            scan_time=timezone.now(),
            allow_entry=True
        )
        self.assertEqual(attendance.status, 'present')
        self.assertTrue(attendance.allow_entry)
    
    def test_attendance_string_representation(self):
        """Test __str__ method"""
        attendance = Attendance.objects.create(
            session=self.session,
            student=self.student,
            status='present'
        )
        expected = f"{self.student.full_name} - {self.session.session_date}"
        self.assertEqual(str(attendance), expected)


class AttendanceViewsTestCase(TestCase):
    """Test attendance views"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='SecurePass123!',
            role='supervisor'
        )
        self.client.login(username='testuser', password='SecurePass123!')
    
    def test_scanner_page_requires_login(self):
        """Test scanner page requires authentication"""
        self.client.logout()
        response = self.client.get(reverse('attendance:scanner'))
        self.assertEqual(response.status_code, 302)
    
    def test_scanner_page_authenticated(self):
        """Test scanner page with authenticated user"""
        response = self.client.get(reverse('attendance:scanner'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'attendance/scanner.html')
    
    def test_process_student_code_empty(self):
        """Test process_student_code with empty code"""
        response = self.client.post(
            reverse('attendance:process_code'),
            data='{"student_code": ""}',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
    
    def test_process_student_code_invalid_json(self):
        """Test process_student_code with invalid JSON"""
        response = self.client.post(
            reverse('attendance:process_code'),
            data='invalid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
