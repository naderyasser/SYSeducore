from django.db import models
from django.utils import timezone


class Session(models.Model):
    """
    Session model for managing class sessions.
    """
    session_id = models.AutoField(primary_key=True)
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    session_date = models.DateField(default=timezone.now)
    
    teacher_attended = models.BooleanField(default=False)
    teacher_checkin_time = models.DateTimeField(null=True, blank=True)
    
    is_cancelled = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)
    
    notification_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'sessions'
        unique_together = ['group', 'session_date']
        ordering = ['-session_date']
    
    def __str__(self):
        return f"{self.group.group_name} - {self.session_date}"


class Attendance(models.Model):
    """
    Attendance model for managing student attendance records.
    """
    STATUS_CHOICES = [
        ('present', 'حاضر'),
        ('late', 'متأخر'),
        ('absent', 'غائب'),
    ]
    
    attendance_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    
    scan_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    rejection_reason = models.CharField(max_length=255, blank=True)
    
    supervisor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='supervised_attendances',
        verbose_name="المشرف المسجل"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'attendances'
        unique_together = ['student', 'session']
        ordering = ['-scan_time']
    
    def __str__(self):
        return f"{self.student.full_name} - {self.status}"


class ActivityLog(models.Model):
    """
    سجل النشاط - لتتبع من قام بكل عملية
    Who is Active? - تسجيل اسم المستخدم (الموظف) في كل عملية
    """
    ACTION_CHOICES = [
        ('student_create', 'إنشاء طالب'),
        ('student_update', 'تعديل طالب'),
        ('student_delete', 'حذف طالب'),
        ('attendance_scan', 'تسجيل حضور'),
        ('payment_create', 'إنشاء دفعة'),
        ('payment_update', 'تعديل دفعة'),
        ('group_create', 'إنشاء مجموعة'),
        ('group_update', 'تعديل مجموعة'),
        ('enrollment_create', 'تسجيل في مجموعة'),
        ('enrollment_remove', 'إزالة من مجموعة'),
        ('override_financial', 'تجاوز القيود المالية'),
        ('override_time', 'تجاوز قيود الوقت'),
    ]

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='activity_logs',
        verbose_name="المستخدم"
    )
    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
        verbose_name="نوع العملية"
    )
    description = models.TextField(
        verbose_name="تفاصيل العملية"
    )
    target_model = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="الموديل المستهدف"
    )
    target_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="معرف السجل"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="عنوان IP"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'activity_logs'
        verbose_name = 'سجل نشاط'
        verbose_name_plural = 'سجلات النشاط'
        ordering = ['-created_at']

    def __str__(self):
        user_name = self.user.get_full_name() if self.user else 'مجهول'
        return f"{user_name} - {self.get_action_display()} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @classmethod
    def log(cls, user, action, description, target_model='', target_id=None, request=None):
        """Helper method to create a log entry"""
        ip_address = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')

        return cls.objects.create(
            user=user,
            action=action,
            description=description,
            target_model=target_model,
            target_id=target_id,
            ip_address=ip_address
        )
