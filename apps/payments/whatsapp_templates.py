"""
WhatsApp Notification Templates for Credit System
Templates for credit-based financial blocking notifications
"""

CREDIT_WHATSAPP_TEMPLATES = {
    # ========================================
    # Payment Block - New Student (No Payment)
    # ========================================
    'payment_block_new': {
        'arabic': """
💳 تنبيه هام - مطلوب دفع - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نود إعلامكم بأن الطالب: {student_name}
لم يتمكن من الدخول لحصة {group_name}

السبب: طالب جديد - يجب تسجيل المصروفات قبل أول حصة

يرجى التوجه للإدارة لتسجيل المصروفات في أقرب وقت.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تنبيه - مطلوب دفع',
        'notification_type': 'payment_block_new',
    },
    
    # ========================================
    # Payment Block - Debt Exceeded
    # ========================================
    'payment_block_debt': {
        'arabic': """
💳 تنبيه هام - مصروفات متأخرة - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نود إعلامكم بأن الطالب: {student_name}
لم يتمكن من الدخول لحصة {group_name}

السبب: لديه {debt} حصة غير مدفوعة
تم تجاوز الحد المسموح (حصتين بدون دفع)

يرجى التوجه للإدارة لتسجيل المصروفات في أقرب وقت.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تنبيه هام - مصروفات متأخرة',
        'notification_type': 'payment_block_debt',
    },
    
    # ========================================
    # Credit Warning (1 session remaining)
    # ========================================
    'credit_warning': {
        'arabic': """
⚠️ تنبيه - nearing credit limit - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

تنبيه للطالب: {student_name}
المجموعة: {group_name}

لديك {remaining_credit} حصة متبقية قبل الحظر المالي
يرجى تجديد المصروفات لتجنب مشاكل في الدخول.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تنبيه - nearing credit limit',
        'notification_type': 'credit_warning',
    },
    
    # ========================================
    # Final Warning (2nd unpaid session)
    # ========================================
    'credit_final_warning': {
        'arabic': """
🚨 تحذير نهائي - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

تحذير نهائي للطالب: {student_name}
المجموعة: {group_name}

لديك 2 حصص غير مدفوعة
الحصة القادمة سيتم الحظر التلقائي!

يرجى التوجه للإدارة فوراً لتسجيل المصروفات.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تحذير نهائي',
        'notification_type': 'credit_final_warning',
    },
    
    # ========================================
    # Payment Recorded Successfully
    # ========================================
    'payment_recorded': {
        'arabic': """
✅ تأكيد استلام دفع - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

نؤكد لكم استلام دفع الطالب: {student_name}
المجموعة: {group_name}
المبلغ: {amount}
عدد الحصص: {sessions_count}

تم تحديث الرصيد بنجاح.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'تأكيد استلام دفع',
        'notification_type': 'payment_recorded',
    },
    
    # ========================================
    # Block Notification (on 3rd attempt)
    # ========================================
    'payment_block_3rd': {
        'arabic': """
🚫 حظر تلقائي - مركز التعليم

السلام عليكم ورحمة الله وبركاته،

تم حظر الطالب: {student_name}
المجموعة: {group_name}

السبب: تجاوز حد الائتمان المسموح
لديه {debt} حصص غير مدفوعة

لن يتمكن الطالب من الدخول حتى يتم تسجيل المصروفات.

يرجى التوجه للإدارة فوراً.

شكراً لتعاونكم.
        """.strip(),
        
        'subject': 'حظر تلقائي',
        'notification_type': 'payment_block_3rd',
    },
}


def get_credit_whatsapp_message(reason, context):
    """
    Get formatted WhatsApp message for credit-related reasons
    
    Args:
        reason: The reason code (payment_block_new, payment_block_debt, etc.)
        context: Dictionary with variables to format:
            - student_name: str
            - group_name: str
            - debt: int (optional)
            - remaining_credit: int (optional)
            - amount: decimal (optional)
            - sessions_count: int (optional)
    
    Returns:
        dict: {
            'message': str,
            'subject': str,
            'notification_type': str
        }
    """
    template = CREDIT_WHATSAPP_TEMPLATES.get(reason)
    
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


# Export for use in other modules
__all__ = ['CREDIT_WHATSAPP_TEMPLATES', 'get_credit_whatsapp_message']
