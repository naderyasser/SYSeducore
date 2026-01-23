"""
Tests for Notification Service and Tasks
"""

from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta, time
from unittest.mock import patch, MagicMock
from apps.teachers.models import Teacher, Group
from apps.students.models import Student
from apps.attendance.models import Session, Attendance
from apps.accounts.models import User
from apps.notifications.tasks import send_attendance_notifications_task
from apps.notifications.services import WhatsAppService, NotificationService


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

        # Create group with session at 10:00 AM
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            schedule_day='Saturday',
            schedule_time=time(10, 0),
            grace_period=10,
            standard_fee=300.00,
            center_percentage=30.00
        )

        # Create student
        self.student = Student.objects.create(
            full_name='Test Student',
            barcode='TEST123',
            group=self.group,
            parent_phone='01234567891',
            financial_status='normal'
        )

        # Create session
        self.session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date(),
            teacher_attended=True
        )

    @patch('apps.notifications.services.requests.post')
    def test_notification_sent_after_10_minutes(self, mock_post):
        """Test that notifications are sent 10 minutes after session start"""
        # Mock successful WhatsApp API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'message_id': '123456'
        }
        mock_post.return_value = mock_response

        # Set current time to 10:10 (exactly 10 minutes after session start)
        test_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(10, 10))
        )

        with patch('django.utils.timezone.now', return_value=test_time):
            # Run the task
            send_attendance_notifications_task()

            # Session should be marked as notification sent
            self.session.refresh_from_db()
            self.assertTrue(self.session.notification_sent)

    @patch('apps.notifications.services.requests.post')
    def test_notification_not_sent_before_10_minutes(self, mock_post):
        """Test that notifications are NOT sent before 10 minutes"""
        # Set current time to 10:05 (only 5 minutes after session start)
        test_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(10, 5))
        )

        with patch('django.utils.timezone.now', return_value=test_time):
            # Run the task
            send_attendance_notifications_task()

            # Session should NOT be marked as notification sent
            self.session.refresh_from_db()
            self.assertFalse(self.session.notification_sent)

    @patch('apps.notifications.services.requests.post')
    def test_notification_sent_after_10_minutes_with_attendance(self, mock_post):
        """Test notification content for present student after 10 minutes"""
        # Mock successful WhatsApp API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'message_id': '123456'
        }
        mock_post.return_value = mock_response

        # Create attendance record
        Attendance.objects.create(
            student=self.student,
            session=self.session,
            status='present',
            scan_time=timezone.make_aware(
                datetime.combine(timezone.now().date(), time(10, 0))
            ),
            supervisor=self.supervisor
        )

        # Set current time to 10:15 (15 minutes after session start)
        test_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(10, 15))
        )

        with patch('django.utils.timezone.now', return_value=test_time):
            # Run the task
            send_attendance_notifications_task()

            # Verify session marked as notification sent
            self.session.refresh_from_db()
            self.assertTrue(self.session.notification_sent)


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
        message = self.service._get_present_message('أحمد محمد', scan_time)

        self.assertIn('أحمد محمد', message)
        self.assertIn('تم تسجيل الحضور', message)
        self.assertIn('حاضر', message)

    def test_late_message_format(self):
        """Test late message format"""
        scan_time = timezone.now()
        message = self.service._get_late_message('أحمد محمد', scan_time)

        self.assertIn('أحمد محمد', message)
        self.assertIn('متأخر', message)

    def test_absent_message_format(self):
        """Test absent message format"""
        message = self.service._get_absent_message('أحمد محمد')

        self.assertIn('أحمد محمد', message)
        self.assertIn('تغيب', message)
        self.assertIn('غياب', message)

    def test_payment_reminder_message_format(self):
        """Test payment reminder message format"""
        message = self.service._get_payment_reminder_message(
            'أحمد محمد',
            'مجموعة الرياضيات',
            300
        )

        self.assertIn('أحمد محمد', message)
        self.assertIn('مجموعة الرياضيات', message)
        self.assertIn('300', message)
        self.assertIn('المصروفات', message)

    def test_warning_message_format(self):
        """Test warning before blocking message format"""
        message = self.service._get_warning_message('أحمد محمد', 300)

        self.assertIn('أحمد محمد', message)
        self.assertIn('300', message)
        self.assertIn('2 حصص', message)
        self.assertIn('منع', message)

    @patch('apps.notifications.services.requests.post')
    def test_send_message_success(self, mock_post):
        """Test successful message sending"""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'message_id': '123456'
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
            'status': 'error',
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
            'أحمد محمد',
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
            'أحمد محمد',
            '01234567890',
            'مجموعة الرياضيات',
            300
        )

        self.assertTrue(result['success'])
        mock_send.assert_called_once()

    @patch.object(WhatsAppService, 'send_warning_before_block')
    def test_send_warning_before_block_whatsapp(self, mock_send):
        """Test sending warning via WhatsApp"""
        mock_send.return_value = {'success': True}

        result = self.service.send_warning_before_block(
            'أحمد محمد',
            '01234567890',
            300
        )

        self.assertTrue(result['success'])
        mock_send.assert_called_once()
