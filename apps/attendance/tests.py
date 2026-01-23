"""
Tests for Attendance Service
"""

from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta
from apps.accounts.models import User
from apps.teachers.models import Teacher, Group
from apps.students.models import Student
from apps.attendance.models import Session, Attendance
from apps.attendance.services import AttendanceService


class AttendanceServiceTest(TestCase):
    
    def setUp(self):
        """Set up test data"""
        # Create teacher
        self.teacher = Teacher.objects.create(
            name='Test Teacher',
            phone='01234567890'
        )
        
        # Create group
        self.group = Group.objects.create(
            name='Test Group',
            subject='Math',
            grade='Grade 1',
            teacher=self.teacher,
            schedule_day='saturday',
            start_time='10:00',
            end_time='12:00'
        )
        
        # Create students
        self.student_normal = Student.objects.create(
            name='Normal Student',
            phone='01234567891',
            group=self.group,
            financial_status='normal',
            barcode='1234567890'
        )
        
        self.student_exempt = Student.objects.create(
            name='Exempt Student',
            phone='01234567892',
            group=self.group,
            financial_status='exempt',
            barcode='1234567891'
        )
        
        # Create session
        self.session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date()
        )
        
        self.service = AttendanceService()
    
    def test_check_time_valid(self):
        """Test time check for valid time"""
        # Within grace period
        session_time = datetime.now().replace(hour=10, minute=0, second=0)
        scan_time = session_time + timedelta(minutes=10)
        
        result = self.service.check_time(scan_time, session_time, 15)
        self.assertTrue(result['passed'])
    
    def test_check_time_late(self):
        """Test time check for late arrival"""
        # Beyond grace period
        session_time = datetime.now().replace(hour=10, minute=0, second=0)
        scan_time = session_time + timedelta(minutes=20)
        
        result = self.service.check_time(scan_time, session_time, 15)
        self.assertFalse(result['passed'])
    
    def test_check_time_too_early(self):
        """Test time check for too early arrival"""
        # More than 30 minutes before
        session_time = datetime.now().replace(hour=10, minute=0, second=0)
        scan_time = session_time - timedelta(minutes=35)
        
        result = self.service.check_time(scan_time, session_time, 15)
        self.assertFalse(result['passed'])
    
    def test_check_day_valid(self):
        """Test day check for valid day"""
        # Saturday
        session_date = timezone.now().replace(
            year=2024, month=1, day=6  # Saturday
        ).date()
        
        result = self.service.check_day(session_date, 'saturday')
        self.assertTrue(result['passed'])
    
    def test_check_day_invalid(self):
        """Test day check for invalid day"""
        # Sunday
        session_date = timezone.now().replace(
            year=2024, month=1, day=7  # Sunday
        ).date()
        
        result = self.service.check_day(session_date, 'saturday')
        self.assertFalse(result['passed'])
    
    def test_check_financial_status_exempt(self):
        """Test financial check for exempt student"""
        result = self.service.check_financial_status(
            self.student_exempt, 
            unpaid_sessions=10
        )
        self.assertTrue(result['passed'])
    
    def test_check_financial_status_normal_paid(self):
        """Test financial check for normal student with paid sessions"""
        result = self.service.check_financial_status(
            self.student_normal,
            unpaid_sessions=2
        )
        self.assertTrue(result['passed'])
    
    def test_check_financial_status_normal_unpaid(self):
        """Test financial check for normal student with unpaid sessions"""
        result = self.service.check_financial_status(
            self.student_normal,
            unpaid_sessions=3
        )
        self.assertFalse(result['passed'])
    
    def test_process_scan_success(self):
        """Test successful barcode scan"""
        result = self.service.process_scan(
            barcode='1234567890',
            session_id=self.session.id,
            scan_time=timezone.now()
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['student']['name'], 'Normal Student')
    
    def test_process_scan_invalid_barcode(self):
        """Test scan with invalid barcode"""
        result = self.service.process_scan(
            barcode='0000000000',
            session_id=self.session.id,
            scan_time=timezone.now()
        )
        
        self.assertFalse(result['success'])
        self.assertIn('message', result)
