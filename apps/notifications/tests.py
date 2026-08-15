"""
Tests for Notification Service and Tasks
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import datetime, timedelta, time
from unittest.mock import patch, MagicMock
from apps.teachers.models import Teacher, Group
from apps.students.models import Student
from apps.attendance.models import Session, Attendance
from apps.accounts.models import User
from apps.notifications.models import WhatsAppMessage
from apps.notifications.tasks import (
    send_attendance_notifications_task,
    send_bulk_whatsapp_task,
    send_monthly_reminders_task,
)
from apps.notifications.services import WhatsAppService, NotificationService


#: Credentials the WhatsApp transport needs before it will attempt a call at
#: all. ``WhatsAppService`` short-circuits with "إعدادات الواتساب غير مكتملة"
#: when either is blank, so tests that assert a *send* must set both — without
#: them the mocked ``requests.post`` is never reached and the assertion fails
#: for a reason that has nothing to do with what is under test.
WAPILOT_TEST_SETTINGS = {
    'WAPILOT_API_TOKEN': 'test-token',
    'WAPILOT_INSTANCE_ID': 'instance-test',
    'WAPILOT_API_BASE_URL': 'https://api.wapilot.net/api/v2',
}


def _api_success():
    """A mocked Wapilot response that the service reads as a success."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {'success': True, 'message_id': '123456'}
    return response


@override_settings(NOTIFICATION_METHOD='whatsapp', **WAPILOT_TEST_SETTINGS)
class NotificationTimingTest(TestCase):
    """
    Test notification timing - should send after 10 minutes.

    ``NOTIFICATION_METHOD`` is forced on: with the test default (``'none'``)
    the task short-circuits and these tests would assert nothing about the
    notification path at all.
    """

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
        from apps.teachers.models import Room
        self.room = Room.objects.create(name='Notif Room', capacity=30)

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
            student_code='NOTIF001',
            full_name='Test Student',
            parent_phone='01234567891',
        )
        from apps.students.models import StudentGroupEnrollment
        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal',
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



@override_settings(**WAPILOT_TEST_SETTINGS)
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
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'success': True,
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

    @patch('apps.notifications.services.requests.post')
    def test_send_message_uses_wapilot_contract(self, mock_post):
        """
        The request must match Wapilot's contract, not the old WASender one.

        This is the regression that cost the centre a working integration: the
        transport kept posting ``{'to': ...}`` with ``Authorization: Bearer`` to
        wasenderapi.com while the account lived on Wapilot, so every send came
        back 401 and no parent was ever notified.
        """
        mock_post.return_value = _api_success()

        self.service.send_message('01234567890', 'Test message')

        args, kwargs = mock_post.call_args
        self.assertEqual(
            args[0], 'https://api.wapilot.net/api/v2/instance-test/send-message'
        )
        # Auth is a bare ``token`` header — not ``Authorization: Bearer``.
        self.assertEqual(kwargs['headers']['token'], 'test-token')
        self.assertNotIn('Authorization', kwargs['headers'])
        # Recipient field is ``chat_id``; ``to`` belonged to the old provider.
        self.assertEqual(kwargs['json']['chat_id'], '201234567890')
        self.assertEqual(kwargs['json']['text'], 'Test message')
        self.assertNotIn('to', kwargs['json'])

    @patch('apps.notifications.services.requests.post')
    def test_dedup_key_is_sent_as_idempotency_header(self, mock_post):
        """A caller's dedup_key must reach Wapilot as ``Idempotency-Key``."""
        mock_post.return_value = _api_success()

        self.service.send_message(
            '01234567890', 'Test message', idempotency_key='attendance:99:5'
        )

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['headers']['Idempotency-Key'], 'attendance:99:5')

    @patch('apps.notifications.services.requests.post')
    def test_no_idempotency_header_when_key_absent(self, mock_post):
        """A human-typed message has no dedup_key; the header must be omitted."""
        mock_post.return_value = _api_success()

        self.service.send_message('01234567890', 'Test message')

        _, kwargs = mock_post.call_args
        self.assertNotIn('Idempotency-Key', kwargs['headers'])

    @patch('apps.notifications.services.requests.post')
    def test_validation_errors_are_surfaced(self, mock_post):
        """A 422's per-field errors are more useful than its generic headline."""
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            'success': False,
            'message': 'Validation failed.',
            'errors': {'chat_id': ['The chat id field is required.']},
            'code': 'VALIDATION_ERROR',
        }
        mock_post.return_value = mock_response

        result = self.service.send_message('01234567890', 'Test message')

        self.assertFalse(result['success'])
        self.assertIn('The chat id field is required.', result['error'])
        self.assertIn('VALIDATION_ERROR', result['error'])

    @patch('apps.notifications.services.requests.post')
    def test_non_json_response_does_not_raise(self, mock_post):
        """An HTML error page from a proxy must fail cleanly, not explode."""
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.json.side_effect = ValueError('no json')
        mock_post.return_value = mock_response

        result = self.service.send_message('01234567890', 'Test message')

        self.assertFalse(result['success'])
        self.assertIn('502', result['error'])


class WhatsAppServiceUnconfiguredTest(TestCase):
    """The transport must refuse to call out when it is not fully configured."""

    @override_settings(WAPILOT_API_TOKEN='', WAPILOT_INSTANCE_ID='instance-test')
    @patch('apps.notifications.services.requests.post')
    def test_missing_token_does_not_call_api(self, mock_post):
        result = WhatsAppService().send_message('01234567890', 'Test')

        self.assertFalse(result['success'])
        mock_post.assert_not_called()

    @override_settings(WAPILOT_API_TOKEN='test-token', WAPILOT_INSTANCE_ID='')
    @patch('apps.notifications.services.requests.post')
    def test_missing_instance_id_does_not_call_api(self, mock_post):
        """
        A blank instance id used to build ``…/api/v2//send-message`` and come
        back 404 — an error that reads like an outage rather than a typo.
        """
        result = WhatsAppService().send_message('01234567890', 'Test')

        self.assertFalse(result['success'])
        mock_post.assert_not_called()


class NotificationServiceTest(TestCase):
    """Test main notification service"""

    def setUp(self):
        """Set up notification service with WhatsApp enabled"""
        self.service = NotificationService()
        self.service.notification_method = 'whatsapp'

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
