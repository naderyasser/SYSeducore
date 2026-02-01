"""
Notification Models - Complete Integration System
"""
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator


class NotificationTemplate(models.Model):
    """
    قوالب الإشعارات المخزنة في قاعدة البيانات
    Database-stored notification templates with version control
    """
    TEMPLATE_TYPES = [
        ('attendance_success', 'حضور ناجح ✅'),
        ('late_block', 'منع تأخير 🔴'),
        ('financial_block_new', 'منع مالي - طالب جديد 🟡'),
        ('financial_block_debt', 'منع مالي - ديون 🟡'),
        ('payment_reminder', 'تذكير بالدفع 📢'),
        ('payment_confirmation', 'تأكيد استلام الدفع 🙏'),
    ]
    
    template_type = models.CharField(
        max_length=50,
        choices=TEMPLATE_TYPES,
        unique=True,
        verbose_name='نوع القالب',
        db_index=True
    )
    template_name = models.CharField(max_length=200, verbose_name='اسم القالب')
    content_arabic = models.TextField(verbose_name='المحتوى بالعربية')
    content_english = models.TextField(blank=True, null=True, verbose_name='المحتوى بالإنجليزية')
    
    # متغيرات القالب المتاحة
    available_variables = models.JSONField(
        default=list,
        verbose_name='المتغيرات المتاحة',
        help_text='قائمة المتغيرات التي يمكن استخدامها في القالب'
    )
    
    # Version Control
    version = models.PositiveIntegerField(default=1, verbose_name='الإصدار')
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_templates',
        verbose_name='أنشأ بواسطة'
    )
    
    class Meta:
        db_table = 'notification_templates'
        ordering = ['template_type']
        verbose_name = 'قالب إشعار'
        verbose_name_plural = 'قوالب الإشعارات'
    
    def __str__(self):
        return f'{self.get_template_type_display()} - v{self.version}'
    
    def render(self, context):
        """
        Render template with given context variables
        
        Args:
            context: Dictionary of variables to replace
            
        Returns:
            str: Rendered message
        """
        try:
            return self.content_arabic.format(**context)
        except KeyError as e:
            # Missing variable, return template with placeholders
            return self.content_arabic
        except Exception as e:
            return f"خطأ في عرض القالب: {str(e)}"
    
    def save(self, *args, **kwargs):
        # Auto-increment version if updating existing template
        if self.pk:
            current = NotificationTemplate.objects.get(pk=self.pk)
            if current.content_arabic != self.content_arabic:
                self.version += 1
        super().save(*args, **kwargs)


class NotificationPreference(models.Model):
    """
    تفضيلات الإشعارات لأولياء الأمور
    Parent notification preferences with opt-out mechanism
    """
    NOTIFICATION_TYPES = [
        ('attendance_success', 'إشعار الحضور الناجح'),
        ('late_block', 'إشعار منع التأخير'),
        ('financial_block', 'إشعار المنع المالي'),
        ('payment_reminder', 'تذكير الدفع اليومي'),
        ('payment_confirmation', 'تأكيد استلام الدفع'),
    ]
    
    student = models.OneToOneField(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='notification_preferences',
        verbose_name='الطالب'
    )
    
    # تفضيلات كل نوع إشعار
    attendance_success_enabled = models.BooleanField(
        default=True,
        verbose_name='إشعار الحضور الناجح',
        help_text='يمكن تعطيله'
    )
    late_block_enabled = models.BooleanField(
        default=True,
        verbose_name='إشعار منع التأخير',
        help_text='إلزامي - لا يمكن تعطيله'
    )
    financial_block_enabled = models.BooleanField(
        default=True,
        verbose_name='إشعار المنع المالي',
        help_text='إلزامي - لا يمكن تعطيله'
    )
    payment_reminder_enabled = models.BooleanField(
        default=True,
        verbose_name='تذكير الدفع اليومي',
        help_text='يمكن تعطيله'
    )
    payment_confirmation_enabled = models.BooleanField(
        default=True,
        verbose_name='تأكيد استلام الدفع',
        help_text='يمكن تعطيله'
    )
    
    # Rate limiting
    messages_last_hour = models.PositiveIntegerField(
        default=0,
        verbose_name='عدد الرسائل في آخر ساعة'
    )
    last_message_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='وقت آخر رسالة'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    class Meta:
        db_table = 'notification_preferences'
        verbose_name = 'تفضيلات الإشعارات'
        verbose_name_plural = 'تفضيلات الإشعارات'
    
    def __str__(self):
        return f'تفضيلات {self.student.full_name}'
    
    def can_send_notification(self, notification_type):
        """
        Check if notification type can be sent
        
        Args:
            notification_type: Type of notification
            
        Returns:
            bool: True if allowed
        """
        # Mandatory notifications cannot be disabled
        if notification_type in ['late_block', 'financial_block']:
            return True
        
        # Check preference for optional notifications
        if notification_type == 'attendance_success':
            return self.attendance_success_enabled
        elif notification_type == 'payment_reminder':
            return self.payment_reminder_enabled
        elif notification_type == 'payment_confirmation':
            return self.payment_confirmation_enabled
        
        return True
    
    def check_rate_limit(self):
        """
        Check if rate limit allows sending (max 5 per hour)
        
        Returns:
            bool: True if under limit
        """
        now = timezone.now()
        one_hour_ago = now - timezone.timedelta(hours=1)
        
        # Reset counter if last message was more than an hour ago
        if self.last_message_time and self.last_message_time < one_hour_ago:
            self.messages_last_hour = 0
            self.save(update_fields=['messages_last_hour'])
        
        return self.messages_last_hour < 5
    
    def increment_message_count(self):
        """Increment message counter for rate limiting"""
        self.messages_last_hour += 1
        self.last_message_time = timezone.now()
        self.save(update_fields=['messages_last_hour', 'last_message_time'])


class NotificationCost(models.Model):
    """
    تتبع تكلفة الإشعارات الشهرية
    Monthly notification cost tracking
    """
    month = models.DateField(verbose_name='الشهر')
    total_messages = models.PositiveIntegerField(default=0, verbose_name='عدد الرسائل')
    total_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='التكلفة الإجمالية'
    )
    cost_per_message = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.0500,
        verbose_name='تكلفة الرسالة'
    )
    currency = models.CharField(max_length=3, default='EGP', verbose_name='العملة')
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    class Meta:
        db_table = 'notification_costs'
        unique_together = ['month']
        ordering = ['-month']
        verbose_name = 'تكلفة الإشعارات'
        verbose_name_plural = 'تكاليف الإشعارات'
    
    def __str__(self):
        return f'{self.month.strftime("%Y-%m")}: {self.total_messages} رسالة = {self.total_cost} {self.currency}'
    
    @classmethod
    def record_message(cls, cost_per_message=0.05):
        """
        Record a sent message and update monthly costs
        
        Args:
            cost_per_message: Cost per single message
        """
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        cost_record, created = cls.objects.get_or_create(
            month=month_start,
            defaults={
                'cost_per_message': cost_per_message
            }
        )
        
        cost_record.total_messages += 1
        cost_record.total_cost += cost_per_message
        cost_record.save()
        
        return cost_record
    
    @classmethod
    def get_monthly_cost(cls, year, month):
        """
        Get cost for a specific month
        
        Args:
            year: Year
            month: Month (1-12)
            
        Returns:
            NotificationCost or None
        """
        month_start = timezone.datetime(year, month, 1).date()
        return cls.objects.filter(month=month_start).first()


class NotificationLog(models.Model):
    """
    سجل الإشعارات المرسلة مع تتبع التسليم والمحاولات
    Enhanced notification log with delivery tracking and retry logic
    """
    NOTIFICATION_TYPES = [
        ('attendance_success', 'حضور ناجح'),
        ('late_block', 'منع تأخير'),
        ('financial_block_new', 'منع مالي - جديد'),
        ('financial_block_debt', 'منع مالي - ديون'),
        ('payment_reminder', 'تذكير دفع'),
        ('payment_confirmation', 'تأكيد دفع'),
        ('custom', 'مخصص'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('sent', 'تم الإرسال'),
        ('delivered', 'تم التسليم'),
        ('failed', 'فشل'),
        ('retrying', 'إعادة المحاولة'),
    ]
    
    # Basic Info
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
    
    # Notification Details
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPES,
        verbose_name='نوع الإشعار',
        db_index=True
    )
    template_used = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs',
        verbose_name='القالب المستخدم'
    )
    message = models.TextField(verbose_name='نص الرسالة')
    
    # Status & Delivery
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='الحالة',
        db_index=True
    )
    
    # API Response
    api_message_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='معرف الرسالة من API'
    )
    api_response = models.JSONField(
        blank=True,
        null=True,
        verbose_name='استجابة API'
    )
    
    # Retry Logic
    retry_count = models.PositiveIntegerField(default=0, verbose_name='عدد محاولات الإعادة')
    max_retries = models.PositiveIntegerField(default=3, verbose_name='أقصى محاولات')
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='موعد إعادة المحاولة القادم'
    )
    
    # Error Tracking
    error_message = models.TextField(blank=True, null=True, verbose_name='رسالة الخطأ')
    error_code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='رمز الخطأ'
    )
    
    # Cost Tracking
    cost = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.0500,
        verbose_name='التكلفة'
    )
    cost_recorded = models.BooleanField(default=False, verbose_name='تم تسجيل التكلفة')
    
    # Timestamps
    sent_at = models.DateTimeField(default=timezone.now, verbose_name='وقت الإرسال')
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='وقت التسليم'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')
    
    # Context Data (for debugging)
    context_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name='بيانات السياق'
    )
    
    class Meta:
        db_table = 'notification_logs'
        ordering = ['-created_at']
        verbose_name = 'سجل إشعار'
        verbose_name_plural = 'سجل الإشعارات'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['notification_type', 'status']),
        ]
    
    def __str__(self):
        return f'{self.get_notification_type_display()} - {self.student_name} - {self.sent_at}'
    
    @property
    def status_badge(self):
        """Get Bootstrap badge class for status"""
        badges = {
            'pending': 'warning',
            'sent': 'info',
            'delivered': 'success',
            'failed': 'danger',
            'retrying': 'secondary',
        }
        return badges.get(self.status, 'secondary')
    
    @property
    def type_icon(self):
        """Get icon for notification type"""
        icons = {
            'attendance_success': 'bi-check-circle text-success',
            'late_block': 'bi-slash-circle text-danger',
            'financial_block_new': 'bi-cash-x text-warning',
            'financial_block_debt': 'bi-exclamation-triangle text-warning',
            'payment_reminder': 'bi-bell text-info',
            'payment_confirmation': 'bi-check2-all text-success',
            'custom': 'bi-chat-dots text-primary',
        }
        return icons.get(self.notification_type, 'bi-bell')
    
    def can_retry(self):
        """Check if notification can be retried"""
        return self.status == 'failed' and self.retry_count < self.max_retries
    
    def schedule_retry(self, delay_minutes=5):
        """
        Schedule a retry with exponential backoff
        
        Args:
            delay_minutes: Base delay in minutes
        """
        if self.can_retry():
            # Exponential backoff: 5min, 10min, 20min
            delay = delay_minutes * (2 ** self.retry_count)
            self.next_retry_at = timezone.now() + timezone.timedelta(minutes=delay)
            self.status = 'retrying'
            self.retry_count += 1
            self.save()
    
    def mark_delivered(self, api_response=None):
        """Mark notification as delivered"""
        self.status = 'delivered'
        self.delivered_at = timezone.now()
        if api_response:
            self.api_response = api_response
        self.save()
    
    def mark_failed(self, error_message, error_code=None):
        """Mark notification as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.error_code = error_code
        self.save()
        
        # Record cost even for failed messages (API charge)
        if not self.cost_recorded:
            NotificationCost.record_message(float(self.cost))
            self.cost_recorded = True
            self.save(update_fields=['cost_recorded'])
