"""
WhatsApp Notification Templates for Attendance System
Templates for different blocking scenarios
"""

WHATSAPP_TEMPLATES = {
    # ========================================
    # Late Arrival (1-10 minutes)
    # ========================================
    'late': {
        'arabic': """
🔴 تنبيه تأخير - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نود إعلامكم بأن الطالب: {student_name}
تأخر عن حصة {group_name} اليوم
مدة التأخير: {minutes_late} دقيقة
تم منع الطالب من الدخول وفقاً للقواعد الصارمة.

يرجى التأكد من وصول الطالب في الوقت المحدد.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تنبيه تأخير',
        'notification_type': 'block_late',
    },
    
    # ========================================
    # Very Late Arrival (10+ minutes)
    # ========================================
    'very_late': {
        'arabic': """
🔴 تنبيه هام - تأخير شديد - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نود إعلامكم بأن الطالب: {student_name}
تأخر تأخيراً شديداً عن حصة {group_name} اليوم
مدة التأخير: {minutes_late} دقيقة
تم منع الطالب من الدخول.

يرجى متابعة الوضع والاتصال بالإدارة في حال وجود ظروف طارئة.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تنبيه هام - تأخير شديد',
        'notification_type': 'block_very_late',
    },
    
    # ========================================
    # Too Early Arrival
    # ========================================
    'too_early': {
        'arabic': """
⏰ تنبيه وصول مبكر - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نود إعلامكم بأن الطالب: {student_name}
حضر مبكراً جداً لحصة {group_name}
الموعد الصحيح: {scheduled_time}

يرجى الالتزام بالموعد المحدد.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تنبيه وصول مبكر',
        'notification_type': 'early_arrival',
    },
    
    # ========================================
    # Payment Issue
    # ========================================
    'payment': {
        'arabic': """
💳 تنبيه مالي - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نود إعلامكم بأن الطالب: {student_name}
لم يتمكن من الدخول لحصة {group_name}
السبب: المصروفات الشهرية غير مدفوعة

يرجى التوجه للإدارة لتسجيل المصروفات في أقرب وقت.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تنبيه مالي',
        'notification_type': 'block_payment',
    },
    
    # ========================================
    # No Session Scheduled
    # ========================================
    'no_session': {
        'arabic': """
📅 تنبيه جدول - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نود إعلامكم بأن الطالب: {student_name}
حاول تسجيل الحضور في وقت غير مجدول له
لا توجد حصة مسجلة له اليوم.

يرجى مراجعة جدول الحصص والتأكد من الأوقات.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تنبيه جدول',
        'notification_type': 'no_session',
    },
    
    # ========================================
    # Success - Attendance Recorded
    # ========================================
    'present': {
        'arabic': """
✅ تأكيد حضور - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نؤكد لكم حضور الطالب: {student_name}
في حصة {group_name} اليوم
وقت الحضور: {scan_time}

نتمنى له دراسة موفقة.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تأكيد حضور',
        'notification_type': 'attendance',
    },
}


def get_whatsapp_message(reason, context):
    """
    Get formatted WhatsApp message for a specific reason
    
    Args:
        reason: The reason code (late, very_late, payment, etc.)
        context: Dictionary with variables to format:
            - student_name: str
            - group_name: str
            - minutes_late: int (optional)
            - scheduled_time: str (optional)
            - scan_time: str (optional)
    
    Returns:
        dict: {
            'message': str,
            'subject': str,
            'notification_type': str
        }
    """
    template = WHATSAPP_TEMPLATES.get(reason)
    
    if not template:
        # Default message
        template = {
            'arabic': 'تنبيه من مركز التعليم بخصوص الطالب: {student_name}',
            'subject': 'تنبيه',
            'notification_type': 'custom'
        }
    
    # Format the message with context
    try:
        message = template['arabic'].format(**context)
    except KeyError as e:
        # Missing context variable, use partial formatting
        message = template['arabic']
        for key, value in context.items():
            message = message.replace(f'{{{key}}}', str(value))
    
    return {
        'message': message,
        'subject': template.get('subject', 'تنبيه'),
        'notification_type': template.get('notification_type', 'custom')
    }


# ========================================
# Notification Service Integration
# ========================================

class WhatsAppNotificationService:
    """
    Service for sending WhatsApp notifications for attendance events
    """
    
    @staticmethod
    def send_blocked_notification(student, group, reason, minutes_late=0):
        """
        Send notification when student is blocked from entry
        
        Args:
            student: Student object
            group: Group object
            reason: Reason code (late, very_late, payment, etc.)
            minutes_late: Minutes late (for time-based blocks)
        """
        from .services import WhatsAppService
        
        # Build context
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name,
            'minutes_late': abs(minutes_late),
            'scheduled_time': group.schedule_time.strftime('%I:%M %p'),
            'scan_time': timezone.now().strftime('%I:%M %p')
        }
        
        # Get formatted message
        notification = get_whatsapp_message(reason, context)
        
        # Send via WhatsApp service
        try:
            whatsapp = WhatsAppService()
            whatsapp.send_message(
                to=student.parent_phone,
                message=notification['message'],
                student=student,
                student_name=student.full_name,
                notification_type=notification['notification_type']
            )
            return True
        except Exception as e:
            print(f"Failed to send WhatsApp notification: {e}")
            return False
    
    @staticmethod
    def send_attendance_confirmation(student, group, scan_time):
        """
        Send confirmation when attendance is recorded successfully
        
        Args:
            student: Student object
            group: Group object
            scan_time: DateTime of scan
        """
        from .services import WhatsAppService
        
        context = {
            'student_name': student.full_name,
            'group_name': group.group_name,
            'scan_time': scan_time.strftime('%I:%M %p')
        }
        
        notification = get_whatsapp_message('present', context)
        
        try:
            whatsapp = WhatsAppService()
            whatsapp.send_message(
                to=student.parent_phone,
                message=notification['message'],
                student=student,
                student_name=student.full_name,
                notification_type=notification['notification_type']
            )
            return True
        except Exception as e:
            print(f"Failed to send WhatsApp notification: {e}")
            return False
