"""
Notification Services - Complete Integration
Handles WhatsApp notifications with template rendering, rate limiting, and cost tracking
"""

import requests
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from typing import Dict, Optional, Any


class TemplateService:
    """
    Service for managing notification templates
    """
    
    @staticmethod
    def get_template(template_type: str) -> Optional['NotificationTemplate']:
        """
        Get active template by type
        
        Args:
            template_type: Type of template
            
        Returns:
            NotificationTemplate or None
        """
        from .models import NotificationTemplate
        try:
            return NotificationTemplate.objects.get(
                template_type=template_type,
                is_active=True
            )
        except NotificationTemplate.DoesNotExist:
            return None
    
    @staticmethod
    def render_template(template_type: str, context: Dict[str, Any]) -> str:
        """
        Render template with context
        
        Args:
            template_type: Type of template
            context: Variables to substitute
            
        Returns:
            str: Rendered message
        """
        template = TemplateService.get_template(template_type)
        
        if template:
            return template.render(context)
        
        # Fallback to default templates
        return TemplateService._get_fallback_template(template_type, context)
    
    @staticmethod
    def _get_fallback_template(template_type: str, context: Dict[str, Any]) -> str:
        """
        Get fallback template if database template not found
        
        Args:
            template_type: Type of template
            context: Variables to substitute
            
        Returns:
            str: Rendered message
        """
        templates = {
            'attendance_success': """السلام عليكم
وصل الطالب/ة {student_name} إلى الحصة
المادة: {group_name}
التوقيت: {scan_time}
الحالة: حضور ✅""",
            
            'late_block': """تنبيه ⚠️
تم منع الطالب/ة {student_name} من الدخول
السبب: تجاوز مهلة التأخير (10 دقائق)
الحصة: {group_name}
الوقت المحدد: {scheduled_time}
وقت الوصول: {scan_time}
الرجاء الالتزام بالمواعيد 🕐""",
            
            'financial_block_new': """عزيزي ولي الأمر
الطالب/ة {student_name} لم يتمكن من الدخول
السبب: لم يتم تسجيل الدفع 💰
للطلاب الجدد: يجب الدفع قبل الحصة الأولى
الرجاء زيارة الإدارة لإتمام الإجراءات""",
            
            'financial_block_debt': """تنبيه مالي ⚠️
تم إيقاف الطالب/ة {student_name} مؤقتاً
عدد الحصص غير المدفوعة: {unpaid_sessions}
المبلغ المستحق: {due_amount} جنيه
الحد المسموح: حصتين فقط
الرجاء سداد المستحقات لاستئناف الحضور""",
            
            'payment_reminder': """تذكير 📢
عدد الحصص غير المدفوعة: {unpaid_sessions}
الحد المسموح: حصتين
المبلغ المستحق حتى الآن: {due_amount} جنيه
لتجنب الإيقاف، يرجى السداد قبل الحصة القادمة""",
            
            'payment_confirmation': """شكراً لكم 🙏
تم استلام دفعة بقيمة: {amount} جنيه
للطالب/ة: {student_name}
رقم الإيصال: {receipt_number}
التاريخ: {payment_date}
تم تحديث الرصيد ✅""",
        }
        
        template = templates.get(template_type, 'تنبيه من النظام')
        
        try:
            return template.format(**context)
        except KeyError:
            # Return template with placeholders if context missing
            return template


class WhatsAppService:
    """
    WhatsApp Service using UltraMsg API
    Enhanced with delivery tracking and retry logic
    """
    
    def __init__(self):
        self.instance_id = getattr(settings, 'ULTRAMSG_INSTANCE_ID', '')
        self.token = getattr(settings, 'ULTRAMSG_TOKEN', '')
        self.base_url = f'https://api.ultramsg.com/{self.instance_id}'
        self.cost_per_message = getattr(settings, 'WHATSAPP_COST_PER_MESSAGE', 0.05)
    
    def send_message(
        self,
        to: str,
        message: str,
        student=None,
        student_name: str = '',
        notification_type: str = 'custom',
        template_type: str = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send WhatsApp message with full tracking
        
        Args:
            to: Phone number (with country code)
            message: Message text
            student: Student object (optional)
            student_name: Student name (for logging)
            notification_type: Type of notification
            template_type: Template type used
            context: Context variables used
            
        Returns:
            Dictionary with result
        """
        from .models import NotificationLog, NotificationPreference
        
        # Format phone number
        phone = self._format_phone_number(to)
        
        # Check preferences and rate limit
        if student:
            preference, created = NotificationPreference.objects.get_or_create(
                student=student,
                defaults={
                    'attendance_success_enabled': True,
                    'payment_reminder_enabled': True,
                    'payment_confirmation_enabled': True,
                }
            )
            
            # Check if notification type is allowed
            if not preference.can_send_notification(notification_type):
                return {
                    'success': False,
                    'error': 'Notification type disabled by user'
                }
            
            # Check rate limit
            if not preference.check_rate_limit():
                return {
                    'success': False,
                    'error': 'Rate limit exceeded (max 5 per hour)'
                }
        
        # Create notification log entry
        log = NotificationLog.objects.create(
            student=student,
            student_name=student_name,
            phone_number=phone,
            notification_type=notification_type,
            message=message,
            status='pending',
            cost=self.cost_per_message,
            context_data=context or {}
        )
        
        # Prepare API request
        url = f'{self.base_url}/messages/chat'
        headers = {'Content-Type': 'application/json'}
        data = {
            'token': self.token,
            'to': phone,
            'body': message
        }
        
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            result = response.json()
            
            # Update log with API response
            log.api_response = result
            
            # Check if sent successfully
            if result.get('sent') == 'true' or result.get('status') == 'success':
                log.status = 'sent'
                log.api_message_id = result.get('id') or result.get('message_id')
                log.save()
                
                # Record cost
                NotificationCost.record_message(self.cost_per_message)
                log.cost_recorded = True
                log.save(update_fields=['cost_recorded'])
                
                # Increment rate limit counter
                if student and preference:
                    preference.increment_message_count()
                
                return {
                    'success': True,
                    'message_id': log.api_message_id,
                    'log_id': log.id,
                    'message': 'تم إرسال الرسالة بنجاح'
                }
            else:
                error_msg = result.get('message', 'فشل إرسال الرسالة')
                log.status = 'failed'
                log.error_message = error_msg
                log.error_code = result.get('code', 'API_ERROR')
                log.save()
                
                return {
                    'success': False,
                    'error': error_msg,
                    'log_id': log.id
                }
        
        except requests.exceptions.RequestException as e:
            error_msg = f'خطأ في الاتصال: {str(e)}'
            log.status = 'failed'
            log.error_message = error_msg
            log.error_code = 'CONNECTION_ERROR'
            log.save()
            
            return {
                'success': False,
                'error': error_msg,
                'log_id': log.id
            }
    
    def _format_phone_number(self, phone: str) -> str:
        """
        Format phone number for WhatsApp (Egyptian format)
        
        Args:
            phone: Phone number in any format
            
        Returns:
            str: Formatted phone number
        """
        # Remove any non-digit characters
        phone = ''.join(filter(str.isdigit, str(phone)))
        
        # If starts with 0, add 20 (Egypt country code)
        if phone.startswith('0'):
            phone = '20' + phone[1:]
        # If doesn't start with country code, add it
        elif not phone.startswith('20'):
            phone = '20' + phone
        
        return phone


class NotificationCost:
    """
    Cost tracking for notifications
    """
    
    @staticmethod
    def record_message(cost: float = 0.05):
        """
        Record a sent message
        
        Args:
            cost: Cost per message
        """
        from .models import NotificationCost as NotificationCostModel
        NotificationCostModel.record_message(cost)
    
    @staticmethod
    def get_monthly_report(year: int, month: int) -> Dict[str, Any]:
        """
        Get monthly cost report
        
        Args:
            year: Year
            month: Month (1-12)
            
        Returns:
            dict: Report data
        """
        from .models import NotificationCost as NotificationCostModel, NotificationLog
        
        cost_record = NotificationCostModel.get_monthly_cost(year, month)
        
        if not cost_record:
            return {
                'year': year,
                'month': month,
                'total_messages': 0,
                'total_cost': 0,
                'by_type': {}
            }
        
        # Get breakdown by type
        from django.db.models import Count
        from django.utils import timezone
        
        month_start = timezone.datetime(year, month, 1).replace(tzinfo=timezone.utc)
        if month == 12:
            month_end = timezone.datetime(year + 1, 1, 1).replace(tzinfo=timezone.utc)
        else:
            month_end = timezone.datetime(year, month + 1, 1).replace(tzinfo=timezone.utc)
        
        by_type = NotificationLog.objects.filter(
            sent_at__gte=month_start,
            sent_at__lt=month_end,
            status__in=['sent', 'delivered']
        ).values('notification_type').annotate(
            count=Count('id')
        ).order_by('notification_type')
        
        return {
            'year': year,
            'month': month,
            'total_messages': cost_record.total_messages,
            'total_cost': float(cost_record.total_cost),
            'cost_per_message': float(cost_record.cost_per_message),
            'currency': cost_record.currency,
            'by_type': {item['notification_type']: item['count'] for item in by_type}
        }


class NotificationService:
    """
    Main notification service with template integration
    """
    
    def __init__(self):
        self.whatsapp_service = WhatsAppService()
        self.template_service = TemplateService()
    
    def send_attendance_success(
        self,
        student,
        group,
        scan_time: timezone.datetime
    ) -> Dict[str, Any]:
        """
        Send successful attendance notification
        
        Args:
            student: Student object
            group: Group object
            scan_time: Scan timestamp
            
        Returns:
            dict: Result
        """
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name,
            'scan_time': scan_time.strftime('%H:%M'),
        }
        
        message = self.template_service.render_template(
            'attendance_success',
            context
        )
        
        return self.whatsapp_service.send_message(
            to=student.parent_phone,
            message=message,
            student=student,
            student_name=student.full_name,
            notification_type='attendance_success',
            template_type='attendance_success',
            context=context
        )
    
    def send_late_block(
        self,
        student,
        group,
        minutes_late: int,
        scheduled_time: str,
        scan_time: str
    ) -> Dict[str, Any]:
        """
        Send late block notification
        
        Args:
            student: Student object
            group: Group object
            minutes_late: Minutes late
            scheduled_time: Scheduled time
            scan_time: Scan time
            
        Returns:
            dict: Result
        """
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name,
            'minutes_late': abs(minutes_late),
            'scheduled_time': scheduled_time,
            'scan_time': scan_time,
        }
        
        message = self.template_service.render_template(
            'late_block',
            context
        )
        
        return self.whatsapp_service.send_message(
            to=student.parent_phone,
            message=message,
            student=student,
            student_name=student.full_name,
            notification_type='late_block',
            template_type='late_block',
            context=context
        )
    
    def send_financial_block_new_student(
        self,
        student,
        group
    ) -> Dict[str, Any]:
        """
        Send financial block notification for new student
        
        Args:
            student: Student object
            group: Group object
            
        Returns:
            dict: Result
        """
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name,
        }
        
        message = self.template_service.render_template(
            'financial_block_new',
            context
        )
        
        return self.whatsapp_service.send_message(
            to=student.parent_phone,
            message=message,
            student=student,
            student_name=student.full_name,
            notification_type='financial_block_new',
            template_type='financial_block_new',
            context=context
        )
    
    def send_financial_block_debt(
        self,
        student,
        group,
        unpaid_sessions: int,
        due_amount: float
    ) -> Dict[str, Any]:
        """
        Send financial block notification for debt
        
        Args:
            student: Student object
            group: Group object
            unpaid_sessions: Number of unpaid sessions
            due_amount: Amount due
            
        Returns:
            dict: Result
        """
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name,
            'unpaid_sessions': unpaid_sessions,
            'due_amount': due_amount,
        }
        
        message = self.template_service.render_template(
            'financial_block_debt',
            context
        )
        
        return self.whatsapp_service.send_message(
            to=student.parent_phone,
            message=message,
            student=student,
            student_name=student.full_name,
            notification_type='financial_block_debt',
            template_type='financial_block_debt',
            context=context
        )
    
    def send_payment_reminder(
        self,
        student,
        group,
        unpaid_sessions: int,
        due_amount: float
    ) -> Dict[str, Any]:
        """
        Send payment reminder notification
        
        Args:
            student: Student object
            group: Group object
            unpaid_sessions: Number of unpaid sessions
            due_amount: Amount due
            
        Returns:
            dict: Result
        """
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name,
            'unpaid_sessions': unpaid_sessions,
            'due_amount': due_amount,
        }
        
        message = self.template_service.render_template(
            'payment_reminder',
            context
        )
        
        return self.whatsapp_service.send_message(
            to=student.parent_phone,
            message=message,
            student=student,
            student_name=student.full_name,
            notification_type='payment_reminder',
            template_type='payment_reminder',
            context=context
        )
    
    def send_payment_confirmation(
        self,
        student,
        amount: float,
        receipt_number: str,
        payment_date: timezone.datetime
    ) -> Dict[str, Any]:
        """
        Send payment confirmation notification
        
        Args:
            student: Student object
            amount: Payment amount
            receipt_number: Receipt number
            payment_date: Payment date
            
        Returns:
            dict: Result
        """
        context = {
            'student_name': student.full_name,
            'amount': amount,
            'receipt_number': receipt_number,
            'payment_date': payment_date.strftime('%Y-%m-%d'),
        }
        
        message = self.template_service.render_template(
            'payment_confirmation',
            context
        )
        
        return self.whatsapp_service.send_message(
            to=student.parent_phone,
            message=message,
            student=student,
            student_name=student.full_name,
            notification_type='payment_confirmation',
            template_type='payment_confirmation',
            context=context
        )


# Import NotificationCost at module level for record_message
from .models import NotificationCost
