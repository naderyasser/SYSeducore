from django.db import models
from django.core.exceptions import ValidationError


class Room(models.Model):
    """
    Room model for managing classrooms.
    موديل القاعات الدراسية
    """
    room_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم القاعة")
    capacity = models.PositiveIntegerField(verbose_name="السعة القصوى")

    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rooms'
        verbose_name = 'قاعة'
        verbose_name_plural = 'القاعات'
        ordering = ['name']

    def __str__(self):
        return self.name


class Teacher(models.Model):
    """
    Teacher model for managing teachers.
    """
    teacher_id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=255, verbose_name="اسم المدرس")
    phone = models.CharField(max_length=17, verbose_name="رقم الهاتف")
    email = models.EmailField(unique=True, verbose_name="البريد الإلكتروني")
    
    specialization = models.CharField(max_length=100, verbose_name="التخصص")
    hire_date = models.DateField(verbose_name="تاريخ التعيين")
    
    # QR Code fields for teacher check-in
    qr_code_base64 = models.TextField(
        blank=True,
        null=True,
        verbose_name="رمز الاستجابة السريعة (QR)",
        help_text="رمز QR للمدرس لتسجيل حضور الحصص"
    )
    qr_code_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ توليد QR",
        help_text="تاريخ آخر توليد لرمز QR"
    )
    
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'teachers'
        verbose_name = 'مدرس'
        verbose_name_plural = 'المدرسين'
        ordering = ['full_name']
    
    def __str__(self):
        return self.full_name
    
    def generate_qr_code(self):
        """Generate QR code for teacher check-in"""
        import qrcode
        import io
        import base64
        from django.utils import timezone
        
        # Generate QR data with teacher identifier
        qr_data = f"TEACHER-{self.teacher_id}"
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        # Update model
        self.qr_code_base64 = f"data:image/png;base64,{img_str}"
        self.qr_code_generated_at = timezone.now()
        self.save(update_fields=['qr_code_base64', 'qr_code_generated_at'])
        
        return self.qr_code_base64


class Group(models.Model):
    """
    Group model for managing student groups.
    نموذج المجموعات الدراسية مع نظام متقدم لحجز القاعات
    """
    DAYS_CHOICES = [
        ('Saturday', 'السبت'),
        ('Sunday', 'الأحد'),
        ('Monday', 'الاثنين'),
        ('Tuesday', 'الثلاثاء'),
        ('Wednesday', 'الأربعاء'),
        ('Thursday', 'الخميس'),
        ('Friday', 'الجمعة'),
    ]
    
    # مدد الجلسات المتاحة (بالدقائق)
    DURATION_CHOICES = [
        (60, 'ساعة واحدة'),
        (90, 'ساعة ونصف'),
        (120, 'ساعتان'),
        (150, 'ساعة ونصف ونصف'),
        (180, '3 ساعات'),
    ]
    
    group_id = models.AutoField(primary_key=True)
    group_name = models.CharField(max_length=100, verbose_name="اسم المجموعة")
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name='groups',
        verbose_name="المدرس"
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        related_name='groups',
        verbose_name="القاعة",
        null=True,
        blank=True
    )

    schedule_day = models.CharField(
        max_length=10,
        choices=DAYS_CHOICES,
        verbose_name="يوم الحصة"
    )
    schedule_time = models.TimeField(verbose_name="وقت بدء الحصة")
    
    # مدة الجلسة بالدقائق (مطلوب لحساب التعارضات الزمنية)
    session_duration = models.PositiveIntegerField(
        choices=DURATION_CHOICES,
        default=120,
        verbose_name="مدة الحصة (دقيقة)",
        help_text="مدة الحصة بالدقائق، تُستخدم للكشف عن التعارضات الزمنية"
    )
    
    standard_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="السعر القياسي"
    )
    center_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=30.00,
        verbose_name="نسبة السنتر %"
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'groups'
        verbose_name = 'مجموعة'
        verbose_name_plural = 'المجموعات'
        ordering = ['schedule_day', 'schedule_time']
        indexes = [
            models.Index(fields=['room', 'schedule_day', 'schedule_time']),
            models.Index(fields=['schedule_day', 'schedule_time']),
            models.Index(fields=['is_active']),
        ]

    def get_end_time(self):
        """
        حساب وقت انتهاء الحصة
        Returns: datetime.time object
        """
        from datetime import datetime, timedelta
        
        if not self.schedule_time:
            return None
            
        # تحويل الوقت إلى datetime للإضافة
        start_datetime = datetime.combine(datetime.today(), self.schedule_time)
        end_datetime = start_datetime + timedelta(minutes=self.session_duration)
        return end_datetime.time()

    def clean(self):
        """
        التحقق المتقدم من عدم وجود تعارض في جدول القاعات
        - يكتشف التعارضات في نفس الوقت تماماً
        - يكتشف التعارضات الزمنية المتداخلة (مع فاصل 15 دقيقة)
        """
        super().clean()

        if not self.room:
            return
            
        if not self.schedule_day or not self.schedule_time:
            return

        # استيراد خدمة جدولة القاعات
        from .services import RoomScheduleService
        
        # استخدام الخدمة للكشف عن التعارضات
        conflict = RoomScheduleService.check_room_conflict(
            room=self.room,
            day=self.schedule_day,
            start_time=self.schedule_time,
            duration=self.session_duration,
            exclude_group_id=self.pk
        )
        
        if conflict:
            raise ValidationError({
                'room': conflict['message_ar'],
                'schedule_time': conflict['message_ar']
            })

    def save(self, *args, skip_validation=False, **kwargs):
        """
        تنفيذ التحقق قبل الحفظ

        Args:
            skip_validation: إذا كان True، يتخطى الـ validation (للـ admin فقط)
        """
        if not skip_validation:
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group_name} - {self.teacher.full_name}"
    
    def get_time_range_display(self):
        """
        عرض نطاق الوقت (البداية - النهاية)
        """
        end_time = self.get_end_time()
        if end_time:
            return f"{self.schedule_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
        return self.schedule_time.strftime('%H:%M')
