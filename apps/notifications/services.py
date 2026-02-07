"""
Notification Services
Handles SMS and WhatsApp notifications
"""

import requests
from django.conf import settings
from django.utils import timezone


class WhatsAppService:
    """
    WhatsApp Service using UltraMsg API
    يدعم الإرسال الفردي والجماعي
    """
    
    def __init__(self):
        self.instance_id = getattr(settings, 'ULTRAMSG_INSTANCE_ID', '')
        self.token = getattr(settings, 'ULTRAMSG_TOKEN', '')
        self.base_url = f'https://api.ultramsg.com/{self.instance_id}'
    
    def send_message(self, to, message):
        """
        Send WhatsApp message
        
        Args:
            to: Phone number (with country code, e.g., 201234567890)
            message: Message text
            
        Returns:
            Dictionary with result
        """
        # Format phone number for Egyptian numbers
        phone = self._format_phone_number(to)
        
        # Prepare API request
        url = f'{self.base_url}/messages/chat'
        headers = {
            'Content-Type': 'application/json',
        }
        data = {
            'token': self.token,
            'to': phone,
            'body': message
        }
        
        try:
            response = requests.post(url, json=data, headers=headers, timeout=10)
            result = response.json()
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'message_id': result.get('message_id'),
                    'message': 'تم إرسال الرسالة بنجاح'
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'فشل إرسال الرسالة')
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'خطأ في الاتصال: {str(e)}'
            }

    def send_bulk_message(self, phone_numbers, message):
        """
        الإرسال الجماعي - إرسال رسالة إلى مجموعة أرقام
        يمكن إرسال تقرير الحضور/الغياب أو التنبيهات إلى قائمة توزيع

        Args:
            phone_numbers: قائمة أرقام الهواتف
            message: نص الرسالة

        Returns:
            Dictionary with results summary
        """
        results = {
            'total': len(phone_numbers),
            'success_count': 0,
            'fail_count': 0,
            'errors': []
        }

        for phone in phone_numbers:
            result = self.send_message(phone, message)
            if result.get('success'):
                results['success_count'] += 1
            else:
                results['fail_count'] += 1
                results['errors'].append({
                    'phone': phone,
                    'error': result.get('error', 'خطأ غير معروف')
                })

        return results

    def send_to_group_chat(self, group_id, message):
        """
        الإرسال إلى مجموعة واتساب
        Send message to a WhatsApp group chat

        Args:
            group_id: WhatsApp group ID
            message: Message text
        """
        url = f'{self.base_url}/messages/chat'
        data = {
            'token': self.token,
            'to': group_id,
            'body': message
        }

        try:
            response = requests.post(url, json=data, timeout=10)
            result = response.json()

            if result.get('status') == 'success':
                return {
                    'success': True,
                    'message': 'تم إرسال الرسالة للمجموعة بنجاح'
                }
            else:
                return {
                    'success': False,
                    'error': result.get('message', 'فشل إرسال الرسالة للمجموعة')
                }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'خطأ في الاتصال: {str(e)}'
            }

    def send_bulk_attendance_report(self, group, session_date=None):
        """
        إرسال تقرير حضور/غياب جماعي لمجموعة كاملة
        """
        from apps.students.models import StudentGroupEnrollment
        from apps.attendance.models import Attendance, Session

        if not session_date:
            session_date = timezone.now().date()

        # Get session
        try:
            session = Session.objects.get(group=group, session_date=session_date)
        except Session.DoesNotExist:
            return {'success': False, 'error': 'لا توجد حصة لهذا التاريخ'}

        # Get all enrollments
        enrollments = StudentGroupEnrollment.objects.filter(
            group=group, is_active=True
        ).select_related('student')

        phone_numbers = []
        message_parts = [
            f'📋 *تقرير الحضور - {group.group_name}*',
            f'📅 التاريخ: {session_date.strftime("%Y/%m/%d")}',
            f'👨‍🏫 المدرس: {group.teacher.full_name}',
            '',
        ]

        present_count = 0
        absent_students = []

        for enrollment in enrollments:
            student = enrollment.student
            attendance = Attendance.objects.filter(
                student=student, session=session
            ).first()

            if attendance:
                message_parts.append(
                    f'✅ {student.full_name} - حاضر ({attendance.scan_time.strftime("%I:%M %p")})'
                )
                present_count += 1
            else:
                message_parts.append(f'❌ {student.full_name} - غائب')
                absent_students.append(student)

            # Collect parent phones
            if student.parent_phone:
                phone_numbers.append(student.parent_phone)

        message_parts.append('')
        message_parts.append(f'📊 الإجمالي: {present_count} حاضر / {len(absent_students)} غائب')
        message_parts.append('')
        message_parts.append('_نظام الحضور الآلي_')

        full_message = '\n'.join(message_parts)

        # Send to all parents
        return self.send_bulk_message(phone_numbers, full_message)
    
    def _format_phone_number(self, phone):
        """
        Format phone number for WhatsApp
        Converts Egyptian numbers to international format
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
    
    def send_attendance_notification(self, student_name, parent_phone, status, time):
        """
        Send attendance notification to parent
        
        Args:
            student_name: Student name
            parent_phone: Parent's phone number
            status: Attendance status (present, late, absent)
            time: Attendance time
        """
        if status == 'present':
            message = self._get_present_message(student_name, time)
        elif status == 'late':
            message = self._get_late_message(student_name, time)
        else:
            message = self._get_absent_message(student_name)
        
        return self.send_message(parent_phone, message)
    
    def send_monthly_reminder(self, student_name, parent_phone, group_name, amount):
        """
        Send monthly payment reminder
        
        Args:
            student_name: Student name
            parent_phone: Parent's phone number
            group_name: Group name
            amount: Amount due
        """
        message = self._get_payment_reminder_message(student_name, group_name, amount)
        return self.send_message(parent_phone, message)
    
    def send_warning_before_block(self, student_name, parent_phone, amount):
        """
        Send warning before blocking student

        Args:
            student_name: Student name
            parent_phone: Parent's phone number
            amount: Amount due
        """
        message = self._get_warning_message(student_name, amount)
        return self.send_message(parent_phone, message)

    def send_block_notification(self, student_name, parent_phone, reason='late'):
        """
        Send notification when student is blocked

        Args:
            student_name: Student name
            parent_phone: Parent's phone number
            reason: Block reason ('late' or 'payment')
        """
        if reason == 'late':
            message = self._get_late_block_message(student_name)
        else:
            message = self._get_payment_block_message(student_name)
        return self.send_message(parent_phone, message)

    def _get_late_block_message(self, student_name):
        """Get late block message"""
        time_str = timezone.now().strftime('%I:%M %p')
        return f'''⛔ *تم منع الدخول - تأخير*

تم منع ابنكم *{student_name}* من دخول الحصة
السبب: التأخر أكثر من 10 دقائق عن الموعد المحدد
الوقت: {time_str}

يُرجى الالتزام بمواعيد الحصص

_نظام الحضور الآلي_'''

    def _get_payment_block_message(self, student_name):
        """Get payment block message"""
        return f'''⛔ *تم منع الدخول - مصروفات*

تم منع ابنكم *{student_name}* من دخول الحصة
السبب: عدم سداد المصروفات المطلوبة

يُرجى مراجعة الإدارة لسداد المصروفات

_نظام الحضور الآلي_'''
    
    def _get_present_message(self, student_name, time):
        """Get present attendance message"""
        time_str = time.strftime('%I:%M %p')
        return f'''✅ *تم تسجيل الحضور*

وصل ابنكم *{student_name}* إلى السنتر بنجاح
الوقت: {time_str}
الحالة: حاضر في الموعد ⏰

_نظام الحضور الآلي_'''
    
    def _get_late_message(self, student_name, time):
        """Get late attendance message"""
        time_str = time.strftime('%I:%M %p')
        return f'''⚠️ *تم تسجيل الحضور - متأخر*

وصل ابنكم *{student_name}* إلى السنتر
الوقت: {time_str}
الحالة: متأخر 🕐

يُرجى الالتزام بالمواعيد المحددة

_نظام الحضور الآلي_'''
    
    def _get_absent_message(self, student_name):
        """Get absence message"""
        date_str = timezone.now().strftime('%Y/%m/%d')
        return f'''❌ *تنبيه غياب*

تغيب ابنكم *{student_name}* عن الحصة اليوم
التاريخ: {date_str}

للاستفسار يُرجى التواصل مع الإدارة

_نظام الحضور الآلي_'''
    
    def _get_payment_reminder_message(self, student_name, group_name, amount):
        """Get payment reminder message"""
        return f'''💰 *تذكير بالمصروفات الشهرية*

عزيزي ولي أمر الطالب *{student_name}*

المجموعة: {group_name}
المصروفات المطلوبة: *{amount} جنيه*

يُرجى سداد المصروفات لضمان استمرار حضور الطالب

للدفع أو الاستفسار يُرجى التواصل مع الإدارة

_نظام الحضور الآلي_'''
    
    def _get_warning_message(self, student_name, amount):
        """Get warning before blocking message"""
        return f'''⚠️ *تنبيه هام - يُرجى الدفع*

عزيزي ولي أمر الطالب *{student_name}*

حضر الطالب 2 حصص هذا الشهر
المبلغ المطلوب: *{amount} جنيه*

⚠️ في حالة عدم السداد، سيتم منع الطالب من حضور الحصة القادمة

يُرجى سرعة السداد

_نظام الحضور الآلي_'''


class NotificationService:
    """
    Main notification service with fallback strategy
    """
    
    def __init__(self):
        self.whatsapp_service = WhatsAppService()
        self.notification_method = getattr(settings, 'NOTIFICATION_METHOD', 'whatsapp')
    
    def send_attendance_notification(self, student_name, parent_phone, status, time):
        """
        Send attendance notification with fallback
        """
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_attendance_notification(
                student_name, parent_phone, status, time
            )
        
        # Add other notification methods here if needed
        
        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}
    
    def send_monthly_reminder(self, student_name, parent_phone, group_name, amount):
        """
        Send monthly payment reminder with fallback
        """
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_monthly_reminder(
                student_name, parent_phone, group_name, amount
            )
        
        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}
    
    def send_warning_before_block(self, student_name, parent_phone, amount):
        """
        Send warning before blocking with fallback
        """
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_warning_before_block(
                student_name, parent_phone, amount
            )

        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}

    def send_block_notification(self, student_name, parent_phone, reason='late'):
        """
        Send block notification with fallback
        """
        if self.notification_method == 'whatsapp':
            return self.whatsapp_service.send_block_notification(
                student_name, parent_phone, reason
            )

        return {'success': False, 'error': 'طريقة الإشعار غير مدعومة'}
