"""
Unit Tests for WhatsApp Notification System
Tests all notification scenarios with mocking
"""

from django.test import TestCase, override_settings
from django.utils import timezone
from unittest.mock import patch, Mock
from datetime import datetime, timedelta
import json

from .models import (
    NotificationTemplate,
    NotificationPreference,
    NotificationLog,
    NotificationCost
)
from .services import (
    TemplateService,
    WhatsAppService,
    NotificationService,
    NotificationCost as NotificationCostService
)
from .tasks import (
    send_attendance_success_task,
    send_late_block_task,
    send_financial_block_new_task,
    send_financial_block_debt_task,
    send_payment_reminder_task,
    send_payment_confirmation_task,
)


class NotificationTemplateTest(TestCase):
    """Test notification template model and rendering"""
    
    def setUp(self):
        self.template = NotificationTemplate.objects.create(
            template_type='attendance_success',
            template_name='حضور ناجح',
            content_arabic='وصل الطالب/ة {student_name} إلى الحصة\nالمادة: {group_name}',
            available_variables=['student_name', 'group_name'],
            is_active=True
        )
    
    def test_template_rendering(self):
        """Test template renders with context variables"""
        context = {
            'student_name': 'أحمد محمد',
            'group_name': 'الرياضيات'
        }
        
        rendered = self.template.render(context)
        
        self.assertIn('أحمد محمد', rendered)
        self.assertIn('الرياضيات', rendered)
    
    def test_template_version_increment(self):
        """Test version increments on update"""
        old_version = self.template.version
        self.template.content_arabic = 'Updated content'
        self.template.save()
        
        self.assertEqual(self.template.version, old_version + 1)
    
    def test_template_missing_variable(self):
        """Test template handles missing variables gracefully"""
        context = {
            'student_name': 'أحمد محمد'
            # Missing group_name
        }
        
        rendered = self.template.render(context)
        
        # Should return template with placeholder
        self.assertIn('أحمد محمد', rendered)


class NotificationPreferenceTest(TestCase):
    """Test notification preference model"""
    
    def setUp(self):
        from apps.students.models import Student
        
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='0123456789'
        )
        
        self.preference = NotificationPreference.objects.create(
            student=self.student,
            attendance_success_enabled=True,
            payment_reminder_enabled=False
        )
    
    def test_can_send_notification_optional(self):
        """Test optional notifications respect preferences"""
        # Attendance success is enabled
        self.assertTrue(
            self.preference.can_send_notification('attendance_success')
        )
        
        # Payment reminder is disabled
        self.assertFalse(
            self.preference.can_send_notification('payment_reminder')
        )
    
    def test_can_send_notification_mandatory(self):
        """Test mandatory notifications cannot be disabled"""
        # Late block is always allowed
        self.assertTrue(
            self.preference.can_send_notification('late_block')
        )
        
        # Financial block is always allowed
        self.assertTrue(
            self.preference.can_send_notification('financial_block')
        )
    
    def test_rate_limit_check(self):
        """Test rate limiting (5 messages per hour)"""
        # Initially under limit
        self.assertTrue(self.preference.check_rate_limit())
        
        # Set to limit
        self.preference.messages_last_hour = 5
        self.preference.save()
        
        # Now over limit
        self.assertFalse(self.preference.check_rate_limit())
    
    def test_rate_limit_reset(self):
        """Test rate limit resets after an hour"""
        self.preference.messages_last_hour = 5
        self.preference.last_message_time = timezone.now() - timedelta(hours=2)
        self.preference.save()
        
        # Should be reset and allowed
        self.assertTrue(self.preference.check_rate_limit())


class WhatsAppServiceTest(TestCase):
    """Test WhatsApp service with mocked API"""
    
    def setUp(self):
        from apps.students.models import Student
        
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='0123456789'
        )
        
        self.service = WhatsAppService()
    
    @override_settings(ULTRAMSG_INSTANCE_ID='test123', ULTRAMSG_TOKEN='token123')
    @patch('apps.notifications.services.requests.post')
    def test_send_message_success(self, mock_post):
        """Test successful message sending"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'sent': 'true',
            'id': 'msg123'
        }
        mock_post.return_value = mock_response
        
        result = self.service.send_message(
            to='0123456789',
            message='Test message',
            student=self.student,
            student_name='أحمد محمد',
            notification_type='test'
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message_id'], 'msg123')
        
        # Check log was created
        log = NotificationLog.objects.filter(
            student=self.student,
            notification_type='test'
        ).first()
        
        self.assertIsNotNone(log)
        self.assertEqual(log.status, 'sent')
    
    @override_settings(ULTRAMSG_INSTANCE_ID='test123', ULTRAMSG_TOKEN='token123')
    @patch('apps.notifications.services.requests.post')
    def test_send_message_failure(self, mock_post):
        """Test message sending failure"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'sent': 'false',
            'message': 'Invalid phone number'
        }
        mock_post.return_value = mock_response
        
        result = self.service.send_message(
            to='0000000000',
            message='Test message',
            student=self.student,
            notification_type='test'
        )
        
        self.assertFalse(result['success'])
        self.assertIn('Invalid phone number', result['error'])
    
    def test_format_phone_number(self):
        """Test phone number formatting for Egypt"""
        # Test with 0 prefix
        phone1 = self.service._format_phone_number('0123456789')
        self.assertEqual(phone1, '20123456789')
        
        # Test without prefix
        phone2 = self.service._format_phone_number('123456789')
        self.assertEqual(phone2, '20123456789')
        
        # Test with country code
        phone3 = self.service._format_phone_number('20123456789')
        self.assertEqual(phone3, '20123456789')


class NotificationServiceTest(TestCase):
    """Test notification service methods"""
    
    def setUp(self):
        from apps.students.models import Student
        from apps.teachers.models import Group
        
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='0123456789'
        )
        
        self.group = Group.objects.create(
            group_name='الرياضيات - المستوى الأول',
            schedule_time='10:00',
            schedule_day='Monday'
        )
        
        self.service = NotificationService()
    
    @patch('apps.notifications.services.WhatsAppService.send_message')
    def test_send_attendance_success(self, mock_send):
        """Test attendance success notification"""
        mock_send.return_value = {'success': True, 'message_id': 'msg123'}
        
        scan_time = timezone.now()
        result = self.service.send_attendance_success(
            self.student,
            self.group,
            scan_time
        )
        
        self.assertTrue(result['success'])
        mock_send.assert_called_once()
        
        # Check message content
        call_args = mock_send.call_args
        message = call_args[1]['message']
        self.assertIn('أحمد محمد', message)
        self.assertIn('الرياضيات', message)
    
    @patch('apps.notifications.services.WhatsAppService.send_message')
    def test_send_late_block(self, mock_send):
        """Test late block notification"""
        mock_send.return_value = {'success': True}
        
        result = self.service.send_late_block(
            self.student,
            self.group,
            minutes_late=5,
            scheduled_time='10:00',
            scan_time='10:05'
        )
        
        self.assertTrue(result['success'])
        
        # Check message content
        call_args = mock_send.call_args
        message = call_args[1]['message']
        self.assertIn('منع', message)
        self.assertIn('5', message)
    
    @patch('apps.notifications.services.WhatsAppService.send_message')
    def test_send_financial_block_new(self, mock_send):
        """Test financial block notification for new student"""
        mock_send.return_value = {'success': True}
        
        result = self.service.send_financial_block_new_student(
            self.student,
            self.group
        )
        
        self.assertTrue(result['success'])
        
        # Check message content
        call_args = mock_send.call_args
        message = call_args[1]['message']
        self.assertIn('لم يتم تسجيل الدفع', message)
    
    @patch('apps.notifications.services.WhatsAppService.send_message')
    def test_send_payment_confirmation(self, mock_send):
        """Test payment confirmation notification"""
        mock_send.return_value = {'success': True}
        
        payment_date = timezone.now()
        result = self.service.send_payment_confirmation(
            self.student,
            amount=500,
            receipt_number='PAY-20240115-123',
            payment_date=payment_date
        )
        
        self.assertTrue(result['success'])
        
        # Check message content
        call_args = mock_send.call_args
        message = call_args[1]['message']
        self.assertIn('500', message)
        self.assertIn('شكراً', message)


class NotificationCostTest(TestCase):
    """Test notification cost tracking"""
    
    def test_record_message(self):
        """Test recording message cost"""
        cost = NotificationCost.record_message(0.05)
        
        self.assertEqual(cost.total_messages, 1)
        self.assertEqual(float(cost.total_cost), 0.05)
    
    def test_monthly_report(self):
        """Test monthly cost report"""
        now = timezone.now()
        
        # Record some messages
        for _ in range(10):
            NotificationCost.record_message(0.05)
        
        report = NotificationCostService.get_monthly_report(
            now.year,
            now.month
        )
        
        self.assertEqual(report['total_messages'], 10)
        self.assertEqual(report['total_cost'], 0.5)


class CeleryTasksTest(TestCase):
    """Test Celery tasks for async notifications"""
    
    def setUp(self):
        from apps.students.models import Student
        from apps.teachers.models import Group
        
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='0123456789'
        )
        
        self.group = Group.objects.create(
            group_name='الرياضيات',
            schedule_time='10:00',
            schedule_day='Monday'
        )
    
    @patch('apps.notifications.tasks.NotificationService')
    def test_attendance_success_task(self, mock_service):
        """Test attendance success Celery task"""
        mock_notification_service = Mock()
        mock_service.return_value = mock_notification_service
        mock_notification_service.send_attendance_success.return_value = {
            'success': True
        }
        
        scan_time = timezone.now()
        result = send_attendance_success_task(
            student_id=self.student.student_id,
            group_id=self.group.group_id,
            scan_time_str=scan_time.isoformat()
        )
        
        self.assertTrue(result['success'])
        mock_notification_service.send_attendance_success.assert_called_once()
    
    @patch('apps.notifications.tasks.NotificationService')
    def test_late_block_task(self, mock_service):
        """Test late block Celery task"""
        mock_notification_service = Mock()
        mock_service.return_value = mock_notification_service
        mock_notification_service.send_late_block.return_value = {
            'success': True
        }
        
        result = send_late_block_task(
            student_id=self.student.student_id,
            group_id=self.group.group_id,
            minutes_late=5,
            scheduled_time='10:00',
            scan_time='10:05'
        )
        
        self.assertTrue(result['success'])
    
    @patch('apps.notifications.tasks.NotificationService')
    def test_payment_confirmation_task(self, mock_service):
        """Test payment confirmation Celery task"""
        mock_notification_service = Mock()
        mock_service.return_value = mock_notification_service
        mock_notification_service.send_payment_confirmation.return_value = {
            'success': True
        }
        
        payment_date = timezone.now()
        result = send_payment_confirmation_task(
            student_id=self.student.student_id,
            amount=500,
            receipt_number='PAY-123',
            payment_date_str=payment_date.isoformat()
        )
        
        self.assertTrue(result['success'])


class NotificationLogTest(TestCase):
    """Test notification log model"""
    
    def setUp(self):
        from apps.students.models import Student
        
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='0123456789'
        )
    
    def test_can_retry(self):
        """Test retry logic"""
        log = NotificationLog.objects.create(
            student=self.student,
            student_name='أحمد محمد',
            phone_number='20123456789',
            notification_type='test',
            message='Test message',
            status='failed',
            retry_count=0,
            max_retries=3
        )
        
        self.assertTrue(log.can_retry())
        
        # After max retries
        log.retry_count = 3
        log.save()
        self.assertFalse(log.can_retry())
    
    def test_schedule_retry(self):
        """Test scheduling retry with exponential backoff"""
        log = NotificationLog.objects.create(
            student=self.student,
            student_name='أحمد محمد',
            phone_number='20123456789',
            notification_type='test',
            message='Test message',
            status='failed',
            retry_count=0,
            max_retries=3
        )
        
        log.schedule_retry()
        
        self.assertEqual(log.retry_count, 1)
        self.assertEqual(log.status, 'retrying')
        self.assertIsNotNone(log.next_retry_at)
    
    def test_mark_delivered(self):
        """Test marking notification as delivered"""
        log = NotificationLog.objects.create(
            student=self.student,
            student_name='أحمد محمد',
            phone_number='20123456789',
            notification_type='test',
            message='Test message',
            status='sent'
        )
        
        api_response = {'delivered': 'true', 'timestamp': '2024-01-15T10:00:00Z'}
        log.mark_delivered(api_response)
        
        self.assertEqual(log.status, 'delivered')
        self.assertIsNotNone(log.delivered_at)
        self.assertEqual(log.api_response, api_response)
    
    def test_mark_failed(self):
        """Test marking notification as failed"""
        log = NotificationLog.objects.create(
            student=self.student,
            student_name='أحمد محمد',
            phone_number='20123456789',
            notification_type='test',
            message='Test message',
            status='pending'
        )
        
        log.mark_failed('Connection timeout', 'TIMEOUT_ERROR')
        
        self.assertEqual(log.status, 'failed')
        self.assertEqual(log.error_message, 'Connection timeout')
        self.assertEqual(log.error_code, 'TIMEOUT_ERROR')


class IntegrationTest(TestCase):
    """Integration tests for notification scenarios"""
    
    def setUp(self):
        from apps.students.models import Student, StudentGroupEnrollment
        from apps.teachers.models import Group
        
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='0123456789'
        )
        
        self.group = Group.objects.create(
            group_name='الرياضيات',
            schedule_time='10:00',
            schedule_day='Monday'
        )
        
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            is_new_student=False,
            credit_balance=2
        )
    
    @patch('apps.notifications.tasks.send_attendance_success_task.delay')
    def test_attendance_success_flow(self, mock_task):
        """Test complete attendance success flow"""
        from apps.attendance.services import AttendanceService
        
        mock_task.return_value = Mock(id='task123')
        
        # Mock current time to be on time
        with patch('apps.attendance.services.timezone.now') as mock_now:
            mock_now.return_value = datetime(
                2024, 1, 15, 10, 0, 0,
                tzinfo=timezone.utc
            )
            
            result = AttendanceService.process_scan('1001', None)
            
            self.assertEqual(result['status'], 'present')
            self.assertTrue(result['allow_entry'])
            
            # Check notification was triggered
            mock_task.assert_called_once()
    
    @patch('apps.notifications.tasks.send_late_block_task.delay')
    def test_late_block_flow(self, mock_task):
        """Test complete late block flow"""
        from apps.attendance.services import AttendanceService
        
        mock_task.return_value = Mock(id='task123')
        
        # Mock current time to be late
        with patch('apps.attendance.services.timezone.now') as mock_now:
            mock_now.return_value = datetime(
                2024, 1, 15, 10, 15, 0,
                tzinfo=timezone.utc
            )
            
            result = AttendanceService.process_scan('1001', None)
            
            self.assertEqual(result['status'], 'late_blocked')
            self.assertFalse(result['allow_entry'])
            
            # Check notification was triggered
            mock_task.assert_called_once()
    
    @patch('apps.notifications.tasks.send_payment_confirmation_task.delay')
    def test_payment_confirmation_flow(self, mock_task):
        """Test complete payment confirmation flow"""
        from apps.payments.services import CreditService
        
        mock_task.return_value = Mock(id='task123')
        
        result = CreditService.record_payment_and_update_credit(
            student=self.student,
            group=self.group,
            amount=500,
            sessions_count=5
        )
        
        self.assertTrue(result['success'])
        
        # Check notification was triggered
        mock_task.assert_called_once()
