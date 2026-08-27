from django.db import models
from django.utils import timezone


class Session(models.Model):
    """
    Session model for managing class sessions.
    """
    session_id = models.AutoField(primary_key=True)
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.PROTECT,
        related_name='sessions'
    )
    session_date = models.DateField(default=timezone.now)

    cycle = models.ForeignKey(
        'teachers.GroupCycle',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='sessions',
        verbose_name="دورة الفوترة",
    )
    sequence_in_cycle = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="ترتيب الحصة في الدورة",
        help_text="فارغ للحصص الملغاة — لا تُحتسب على أي طالب",
    )

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

    def get_room(self):
        """
        قاعة هذه الحصة تحديدًا — كل يوم في المجموعة له قاعته الخاصة، فتُشتق من
        الموعد المطابق ليوم أسبوع ``session_date`` وليس من المجموعة ككل.
        """
        entry = self.group.get_schedule_for_day(self.session_date.strftime('%A'))
        return entry.room if entry else None


class Attendance(models.Model):
    """
    Attendance model for managing student attendance records.
    """
    STATUS_CHOICES = [
        ('present', 'حاضر'),
        ('late', 'متأخر'),
        ('absent', 'غائب'),
        ('exception', 'استثناء'),
    ]
    
    attendance_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='attendances'
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.PROTECT,
        related_name='attendances'
    )
    
    scan_time = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES)
    rejection_reason = models.CharField(max_length=255, blank=True)
    
    supervisor = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='supervised_attendances',
        verbose_name="المشرف المسجل"
    )

    exception_record = models.ForeignKey(
        'ExceptionRecord',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendances',
        verbose_name="سجل الاستثناء المرتبط",
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
        ('student_toggle', 'تغيير حالة طالب'),
        ('attendance_scan', 'تسجيل حضور'),
        ('session_cancel', 'إلغاء حصة'),
        ('teacher_checkin', 'تسجيل حضور مدرس'),
        ('payment_create', 'إنشاء دفعة'),
        ('payment_update', 'تعديل دفعة'),
        ('payment_record', 'تسجيل دفعة'),
        ('teacher_create', 'إضافة مدرس'),
        ('teacher_update', 'تعديل مدرس'),
        ('teacher_delete', 'حذف مدرس'),
        ('group_create', 'إنشاء مجموعة'),
        ('group_update', 'تعديل مجموعة'),
        ('group_delete', 'حذف مجموعة'),
        ('room_create', 'إضافة قاعة'),
        ('room_update', 'تعديل قاعة'),
        ('room_delete', 'حذف قاعة'),
        ('subject_create', 'إضافة مادة'),
        ('subject_update', 'تعديل مادة'),
        ('subject_delete', 'حذف مادة'),
        ('user_create', 'إنشاء مستخدم'),
        ('user_update', 'تعديل مستخدم'),
        ('user_toggle', 'تغيير حالة مستخدم'),
        ('enrollment_create', 'تسجيل في مجموعة'),
        ('enrollment_remove', 'إزالة من مجموعة'),
        ('override_financial', 'تجاوز القيود المالية'),
        ('override_time', 'تجاوز قيود الوقت'),
        ('exception_grant', 'منح استثناء'),
        ('exception_revoke', 'إلغاء استثناء'),
        ('settlement_create', 'إنشاء كشف تسوية'),
        ('settlement_update', 'تعديل كشف تسوية'),
        ('settlement_approve', 'اعتماد كشف تسوية'),
        ('settlement_reopen', 'إعادة فتح كشف تسوية'),
        # Recycle-bin actions (apps.reports) — they used to be written as the
        # generic 'update'/'delete', which are not valid choices, so
        # get_action_display() echoed the raw string and the filter dropdown
        # could not select them.
        ('restore', 'استعادة من سلة المحذوفات'),
        ('permanent_delete', 'حذف نهائي'),
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


class ExceptionRecord(models.Model):
    """
    سجل الاستثناءات — لتسجيل حالات استثناء الدفع والتأخير
    Exception records for payment overrides and late-arrival overrides.
    """
    EXCEPTION_TYPE_CHOICES = [
        ('payment', 'استثناء دفع — Payment Exception'),
        ('late_arrival', 'استثناء تأخير — Late Arrival Exception'),
    ]

    PREDEFINED_REASON_CHOICES = [
        ('forgot_money', 'نسي المصروفات – Forgot money'),
        ('another_class', 'كان في حصة أخرى – Was attending another class'),
        ('transportation', 'تأخر بسبب المواصلات – Delayed by transportation'),
        ('medical', 'ظروف صحية طارئة – Medical emergency'),
        ('family_emergency', 'ظرف عائلي طارئ – Family emergency'),
        ('system_error', 'خطأ في النظام – System error'),
        ('admin_override', 'تجاوز إداري – Administrative override'),
        ('other', 'سبب آخر – Other'),
    ]

    exception_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='exception_records',
        verbose_name="الطالب",
    )
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.PROTECT,
        related_name='exception_records',
        null=True,
        blank=True,
        verbose_name="المجموعة",
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exception_records',
        verbose_name="الحصة المرتبطة",
    )
    exception_type = models.CharField(
        max_length=20,
        choices=EXCEPTION_TYPE_CHOICES,
        verbose_name="نوع الاستثناء",
    )
    reason_type = models.CharField(
        max_length=30,
        choices=PREDEFINED_REASON_CHOICES,
        default='other',
        verbose_name="سبب الاستثناء",
    )
    custom_reason = models.TextField(
        blank=True,
        verbose_name="سبب مخصص",
        help_text="تفاصيل إضافية إن كان السبب 'آخر' أو لتوضيح أكثر",
    )
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='granted_exceptions',
        verbose_name="تمت الموافقة بواسطة",
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        db_table = 'exception_records'
        verbose_name = 'سجل استثناء'
        verbose_name_plural = 'سجلات الاستثناءات'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.full_name} — {self.get_exception_type_display()} — {self.get_reason_type_display()}"

    @property
    def reason_display(self):
        """Returns full reason text including custom part."""
        base = self.get_reason_type_display()
        if self.custom_reason:
            return f"{base} — {self.custom_reason}"
        return base
