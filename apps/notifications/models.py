"""
Notification Models
"""
from django.db import models
from django.utils import timezone


class NotificationLog(models.Model):
    """
    سجل الإشعارات المرسلة
    """
    NOTIFICATION_TYPES = [
        ('attendance', 'حضور'),
        ('late', 'تأخير'),
        ('absent', 'غياب'),
        ('payment_reminder', 'تذكير بالدفع'),
        ('payment_warning', 'تحذير قبل الحظر'),
        ('block_late', 'منع - تأخير'),
        ('block_payment', 'منع - مصروفات'),
        ('custom', 'مخصص'),
    ]

    STATUS_CHOICES = [
        ('sent', 'تم الإرسال'),
        ('failed', 'فشل'),
        ('pending', 'قيد الانتظار'),
    ]

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name='الطالب'
    )
    student_name = models.CharField(max_length=255, verbose_name='اسم الطالب')
    phone_number = models.CharField(max_length=20, verbose_name='رقم الهاتف')
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        verbose_name='نوع الإشعار'
    )
    message = models.TextField(verbose_name='نص الرسالة')
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة'
    )
    error_message = models.TextField(blank=True, null=True, verbose_name='رسالة الخطأ')
    sent_at = models.DateTimeField(default=timezone.now, verbose_name='وقت الإرسال')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')

    class Meta:
        db_table = 'notification_logs'
        ordering = ['-sent_at']
        verbose_name = 'سجل إشعار'
        verbose_name_plural = 'سجل الإشعارات'

    def __str__(self):
        return f'{self.get_notification_type_display()} - {self.student_name} - {self.sent_at}'

    @property
    def status_badge(self):
        """Get Bootstrap badge class for status"""
        badges = {
            'sent': 'success',
            'failed': 'danger',
            'pending': 'warning',
        }
        return badges.get(self.status, 'secondary')

    @property
    def type_icon(self):
        """Get icon for notification type"""
        icons = {
            'attendance': 'bi-check-circle text-success',
            'late': 'bi-clock text-warning',
            'absent': 'bi-x-circle text-danger',
            'payment_reminder': 'bi-cash-coin text-info',
            'payment_warning': 'bi-exclamation-triangle text-warning',
            'block_late': 'bi-slash-circle text-danger',
            'block_payment': 'bi-slash-circle text-danger',
            'custom': 'bi-chat-dots text-primary',
        }
        return icons.get(self.notification_type, 'bi-bell')
