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
    STRICT MODE: No tolerance for late arrivals.
    """
    # Status choices with color codes and entry permissions
    STATUS_CHOICES = [
        ('present', 'حاضر', 'green', True),           # On time or early - ALLOWED
        ('late_blocked', 'ممنوع - تأخير', 'red', False),  # 1-10 min late - BLOCKED
        ('very_late', 'ممنوع - تأخير شديد', 'red', False), # 10+ min late - BLOCKED
        ('no_session', 'لا توجد حصة', 'white', False),     # No session - BLOCKED
        ('blocked_payment', 'ممنوع - مصروفات', 'yellow', False),  # Payment issue - BLOCKED
        ('blocked_other', 'ممنوع', 'gray', False),      # Other reason - BLOCKED
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
    
    # Status with choice structure
    status = models.CharField(
        max_length=20,
        choices=[(choice[0], choice[1]) for choice in STATUS_CHOICES]
    )
    
    # New fields for strict mode
    color_code = models.CharField(
        max_length=20,
        choices=[(choice[2], choice[2]) for choice in STATUS_CHOICES],
        default='white',
        verbose_name='كود اللون',
        help_text='لون عرض الحالة على شاشة الكشك'
    )
    
    allow_entry = models.BooleanField(
        default=False,
        verbose_name='السماح بالدخول',
        help_text='هل يُسمح للطالب بالدخول أم لا'
    )
    
    rejection_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='سبب الرفض'
    )
    
    # Time tracking for audit trail
    minutes_late = models.IntegerField(
        default=0,
        verbose_name='دقائق التأخير',
        help_text='عدد الدقائق المتأخرة (سالب للوصول المبكر)'
    )
    
    # Supervisor who recorded this attendance
    supervisor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='supervised_attendances'
    )
    
    # Notification tracking
    parent_notified = models.BooleanField(
        default=False,
        verbose_name='تم إخطار ولي الأمر'
    )
    notification_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='وقت إرسال الإخطار'
    )
    notification_type = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='نوع الإخطار'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'attendances'
        unique_together = ['student', 'session']
        ordering = ['-scan_time']
        indexes = [
            models.Index(fields=['status', 'allow_entry']),
            models.Index(fields=['scan_time']),
            models.Index(fields=['color_code']),
        ]
    
    def __str__(self):
        return f"{self.student.full_name} - {self.get_status_display()}"
    
    @property
    def status_display_arabic(self):
        """Get Arabic display text for status"""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)
    
    @property
    def is_allowed(self):
        """Check if entry is allowed"""
        return self.allow_entry
    
    @property
    def color_class(self):
        """Get Bootstrap color class for this status"""
        color_map = {
            'green': 'success',
            'red': 'danger',
            'yellow': 'warning',
            'white': 'light',
            'gray': 'secondary'
        }
        return color_map.get(self.color_code, 'secondary')
    
    def get_full_status_dict(self):
        """Get complete status information"""
        status_dict = dict(self.STATUS_CHOICES)
        for code, arabic, color, allowed in self.STATUS_CHOICES:
            if code == self.status:
                return {
                    'code': code,
                    'arabic': arabic,
                    'color': color,
                    'allowed': allowed,
                    'minutes_late': self.minutes_late,
                    'rejection_reason': self.rejection_reason
                }
        return None


class BlockedAttempt(models.Model):
    """
    Audit trail for all blocked attendance attempts.
    Keeps record of students who were denied entry.
    """
    REASON_CHOICES = [
        ('late', 'تأخير'),
        ('very_late', 'تأخير شديد'),
        ('no_session', 'لا توجد حصة'),
        ('payment', 'مصروفات'),
        ('other', 'أخرى'),
    ]
    
    attempt_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='blocked_attempts'
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='blocked_attempts',
        null=True,
        blank=True
    )
    
    attempt_time = models.DateTimeField(default=timezone.now, verbose_name='وقت المحاولة')
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        verbose_name='سبب المنع'
    )
    minutes_late = models.IntegerField(
        default=0,
        verbose_name='دقائق التأخير'
    )
    
    # Session information (denormalized for quick reference)
    group_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='اسم المجموعة'
    )
    scheduled_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name='الوقت المجدول'
    )
    
    # Parent notification
    parent_notified = models.BooleanField(
        default=False,
        verbose_name='تم إخطار ولي الأمر'
    )
    notification_message = models.TextField(
        blank=True,
        verbose_name='رسالة الإخطار'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'blocked_attempts'
        ordering = ['-attempt_time']
        indexes = [
            models.Index(fields=['student', 'attempt_time']),
            models.Index(fields=['reason']),
            models.Index(fields=['attempt_time']),
        ]
        verbose_name = 'محاولة دخول ممنوعة'
        verbose_name_plural = 'محاولات الدخول الممنوعة'
    
    def __str__(self):
        return f"{self.student.full_name} - {self.get_reason_display()} - {self.attempt_time.strftime('%Y-%m-%d %H:%M')}"


class KioskDevice(models.Model):
    """
    Kiosk Device model for managing QR scanning devices.
    Each kiosk is bound to a specific room.
    """
    device_id = models.CharField(
        max_length=50,
        unique=True,
        primary_key=True,
        verbose_name="معرف الجهاز",
        help_text="معرف فريد للجهاز (مثال: KIOSK-001)"
    )
    device_name = models.CharField(
        max_length=100,
        verbose_name="اسم الجهاز",
        help_text="اسم وصفي للجهاز (مثال: جهاز القاعة 1)"
    )
    room = models.ForeignKey(
        'teachers.Room',
        on_delete=models.PROTECT,
        related_name='kiosks',
        verbose_name="القاعة المرتبطة",
        help_text="القاعة التي يخدمها هذا الجهاز"
    )
    
    is_active = models.BooleanField(
        default=True,
        verbose_name="نشط",
        help_text="هل الجهاز يعمل حالياً؟"
    )
    
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="آخر اتصال",
        help_text="آخر مرة أرسل فيها الجهاز إشارة حياة"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'kiosk_devices'
        verbose_name = 'جهاز مسح ضوئي'
        verbose_name_plural = 'أجهزة المسح الضوئي'
        ordering = ['device_id']
    
    def __str__(self):
        return f"{self.device_name} ({self.room.name})"
    
    def get_current_session(self):
        """Get the currently active session for this kiosk's room"""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        current_time = now.time()
        current_day = now.strftime('%A')
        
        # Get groups scheduled for this room at this time
        from apps.teachers.models import Group
        groups = Group.objects.filter(
            room=self.room,
            schedule_day=current_day,
            is_active=True
        )
        
        for group in groups:
            start_time = group.schedule_time
            end_time = (
                timezone.datetime.combine(timezone.now().date(), start_time) +
                timedelta(minutes=group.duration)
            ).time()
            
            # Check if current time is within session window (30 min before to end)
            early_window = (
                timezone.datetime.combine(timezone.now().date(), start_time) -
                timedelta(minutes=30)
            ).time()
            
            if early_window <= current_time <= end_time:
                # Get or create session for today
                session, _ = Session.objects.get_or_create(
                    group=group,
                    session_date=now.date()
                )
                return session
        
        return None

