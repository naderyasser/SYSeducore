"""
Tests for Notification Service and Tasks
"""

from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta, time
from unittest.mock import patch, MagicMock
from apps.teachers.models import Teacher, Group, Room
from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Session, Attendance
from apps.accounts.models import User
from apps.notifications.services import WhatsAppService, NotificationService
from apps.notifications.models import NotificationLog


class NotificationTimingTest(TestCase):
    """Test notification timing - should send after 10 minutes"""

    def setUp(self):
        """Set up test data"""
        # Create supervisor
        self.supervisor = User.objects.create_user(
            username='supervisor',
            password='testpass123',
            role='supervisor'
        )

        # Create teacher
        self.teacher = Teacher.objects.create(
            full_name='Test Teacher',
            phone='01234567890',
            email='teacher@test.com',
            specialization='Math',
            hire_date=timezone.now().date()
        )

        # Create room
        self.room = Room.objects.create(
            name='Test Room',
            capacity=30
        )

        # Create group with session at 10:00 AM
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(10, 0),
            standard_fee=300.00,
            center_percentage=30.00
        )

        # Create student
        self.student = Student.objects.create(
            student_code='TEST001',
            full_name='Test Student',
            parent_phone='01234567891'
        )

        # Enroll student in group
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

        # Create session
        self.session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date(),
            teacher_attended=True
        )

    @patch('apps.notifications.services.requests.post')
    def test_notification_sent_successfully(self, mock_post):
        """Test that WhatsApp notifications can be sent"""
        # Mock successful WhatsApp API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'sent': 'true',
            'id': '123456',
            'message': 'ok'
        }
        mock_post.return_value = mock_response

        # Send notification
        ws = WhatsAppService()
        result = ws.send_message(
            to=self.student.parent_phone,
            message='Test message',
            student=self.student,
            student_name=self.student.full_name,
            notification_type='custom'
        )

        # Check result
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], '123456')

        # Check notification was logged
        log = NotificationLog.objects.filter(student=self.student).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'sent')

    @patch('apps.notifications.services.requests.post')
    def test_notification_failure_logged(self, mock_post):
        """Test that failed notifications are logged"""
        # Mock failed WhatsApp API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'sent': 'false',
            'message': 'Invalid phone number'
        }
        mock_post.return_value = mock_response

        # Send notification
        ws = WhatsAppService()
        result = ws.send_message(
            to='invalid',
            message='Test message',
            student=self.student,
            student_name=self.student.full_name,
            notification_type='custom'
        )

        # Check result
        self.assertFalse(result['success'])

        # Check notification was logged as failed
        log = NotificationLog.objects.filter(student=self.student).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'failed')

    @patch('apps.notifications.services.requests.post')
    def test_attendance_notification(self, mock_post):
        """Test attendance notification messages"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'sent': 'true',
            'id': '123456'
        }
        mock_post.return_value = mock_response

        ws = WhatsAppService()

        # Test present message
        result = ws.send_attendance_notification(
            student_name=self.student.full_name,
            parent_phone=self.student.parent_phone,
            status='present',
            time=timezone.now(),
            student=self.student
        )
        self.assertTrue(result['success'])

        # Check log has correct notification type
        log = NotificationLog.objects.filter(notification_type='attendance').first()
        self.assertIsNotNone(log)

    @patch('apps.notifications.services.requests.post')
    def test_block_notification(self, mock_post):
        """Test block notification messages"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'sent': 'true',
            'id': '123456'
        }
        mock_post.return_value = mock_response

        ws = WhatsAppService()

        # Test late block message
        result = ws.send_block_notification(
            student_name=self.student.full_name,
            parent_phone=self.student.parent_phone,
            reason='late',
            student=self.student
        )
        self.assertTrue(result['success'])

        # Check log has correct notification type
        log = NotificationLog.objects.filter(notification_type='block_late').first()
        self.assertIsNotNone(log)

    def test_phone_number_formatting(self):
        """Test phone number formatting for Egyptian numbers"""
        ws = WhatsAppService()

        # Test various formats
        self.assertEqual(ws._format_phone_number('01012345678'), '201012345678')
        self.assertEqual(ws._format_phone_number('1012345678'), '201012345678')
        self.assertEqual(ws._format_phone_number('201012345678'), '201012345678')
        self.assertEqual(ws._format_phone_number('+201012345678'), '201012345678')


class NotificationLogModelTest(TestCase):
    """Test NotificationLog model"""

    def setUp(self):
        """Set up test data"""
        self.student = Student.objects.create(
            student_code='LOG001',
            full_name='Log Test Student',
            parent_phone='01234567890'
        )

    def test_notification_log_creation(self):
        """Test creating a notification log entry"""
        log = NotificationLog.objects.create(
            student=self.student,
            student_name=self.student.full_name,
            phone_number='201234567890',
            notification_type='attendance',
            message='Test message',
            status='sent'
        )

        self.assertEqual(log.student, self.student)
        self.assertEqual(log.notification_type, 'attendance')
        self.assertEqual(log.status, 'sent')

    def test_status_badge(self):
        """Test status badge property"""
        log = NotificationLog(status='sent')
        self.assertEqual(log.status_badge, 'success')

        log.status = 'failed'
        self.assertEqual(log.status_badge, 'danger')

        log.status = 'pending'
        self.assertEqual(log.status_badge, 'warning')

    def test_type_icon(self):
        """Test type icon property"""
        log = NotificationLog(notification_type='attendance')
        self.assertIn('check-circle', log.type_icon)

        log.notification_type = 'late'
        self.assertIn('clock', log.type_icon)

        log.notification_type = 'block_late'
        self.assertIn('slash-circle', log.type_icon)


class WhatsAppServiceTest(TestCase):
    """Test WhatsApp service methods"""

    def setUp(self):
        """Set up WhatsApp service"""
        self.service = WhatsAppService()

    def test_format_phone_number_with_zero(self):
        """Test phone number formatting starting with 0"""
        phone = self.service._format_phone_number('01234567890')
        self.assertEqual(phone, '201234567890')

    def test_format_phone_number_without_country_code(self):
        """Test phone number formatting without country code"""
        phone = self.service._format_phone_number('1234567890')
        self.assertEqual(phone, '201234567890')

    def test_format_phone_number_with_country_code(self):
        """Test phone number formatting with country code"""
        phone = self.service._format_phone_number('201234567890')
        self.assertEqual(phone, '201234567890')

    def test_present_message_format(self):
        """Test present message format"""
        scan_time = timezone.now()
        message = self.service._get_present_message('Test Student', scan_time)

        self.assertIn('Test Student', message)
        self.assertIn('تم تسجيل الحضور', message)
        self.assertIn('حاضر', message)

    def test_late_message_format(self):
        """Test late message format"""
        scan_time = timezone.now()
        message = self.service._get_late_message('Test Student', scan_time)

        self.assertIn('Test Student', message)
        self.assertIn('متأخر', message)

    def test_absent_message_format(self):
        """Test absent message format"""
        message = self.service._get_absent_message('Test Student')

        self.assertIn('Test Student', message)
        self.assertIn('تغيب', message)
        self.assertIn('غياب', message)

    def test_payment_reminder_message_format(self):
        """Test payment reminder message format"""
        message = self.service._get_payment_reminder_message(
            'Test Student',
            'Math Group',
            300
        )

        self.assertIn('Test Student', message)
        self.assertIn('Math Group', message)
        self.assertIn('300', message)
        self.assertIn('المصروفات', message)

    def test_warning_message_format(self):
        """Test warning before blocking message format"""
        message = self.service._get_warning_message('Test Student', 300)

        self.assertIn('Test Student', message)
        self.assertIn('300', message)
        self.assertIn('2 حصص', message)
        self.assertIn('منع', message)

    @patch('apps.notifications.services.requests.post')
    def test_send_message_success(self, mock_post):
        """Test successful message sending"""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'sent': 'true',
            'id': '123456'
        }
        mock_post.return_value = mock_response

        result = self.service.send_message('01234567890', 'Test message')

        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], '123456')

    @patch('apps.notifications.services.requests.post')
    def test_send_message_failure(self, mock_post):
        """Test failed message sending"""
        # Mock failed API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'sent': 'false',
            'message': 'Invalid token'
        }
        mock_post.return_value = mock_response

        result = self.service.send_message('01234567890', 'Test message')

        self.assertFalse(result['success'])
        self.assertIn('error', result)


class NotificationServiceTest(TestCase):
    """Test main notification service"""

    def setUp(self):
        """Set up notification service"""
        self.service = NotificationService()

    @patch.object(WhatsAppService, 'send_attendance_notification')
    def test_send_attendance_notification_whatsapp(self, mock_send):
        """Test sending attendance notification via WhatsApp"""
        mock_send.return_value = {'success': True}

        result = self.service.send_attendance_notification(
            'Test Student',
            '01234567890',
            'present',
            timezone.now()
        )

        self.assertTrue(result['success'])
        mock_send.assert_called_once()

    @patch.object(WhatsAppService, 'send_monthly_reminder')
    def test_send_monthly_reminder_whatsapp(self, mock_send):
        """Test sending monthly reminder via WhatsApp"""
        mock_send.return_value = {'success': True}

        result = self.service.send_monthly_reminder(
            'Test Student',
            '01234567890',
            'Math Group',
            300
        )

        self.assertTrue(result['success'])
        mock_send.assert_called_once()

    @patch.object(WhatsAppService, 'send_warning_before_block')
    def test_send_warning_before_block_whatsapp(self, mock_send):
        """Test sending warning via WhatsApp"""
        mock_send.return_value = {'success': True}

        result = self.service.send_warning_before_block(
            'Test Student',
            '01234567890',
            300
        )

        self.assertTrue(result['success'])
        mock_send.assert_called_once()

    @patch.object(WhatsAppService, 'send_block_notification')
    def test_send_block_notification_whatsapp(self, mock_send):
        """Test sending block notification via WhatsApp"""
        mock_send.return_value = {'success': True}

        result = self.service.send_block_notification(
            'Test Student',
            '01234567890',
            reason='late'
        )

        self.assertTrue(result['success'])
        mock_send.assert_called_once()
