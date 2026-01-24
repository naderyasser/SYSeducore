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


class Group(models.Model):
    """
    Group model for managing student groups.
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
    schedule_time = models.TimeField(verbose_name="وقت الحصة")
    
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
    
    class Meta:
        db_table = 'groups'
        verbose_name = 'مجموعة'
        verbose_name_plural = 'المجموعات'
        constraints = [
            models.UniqueConstraint(
                fields=['room', 'schedule_day', 'schedule_time'],
                name='unique_room_schedule',
                violation_error_message='يوجد تعارض: القاعة محجوزة في نفس اليوم والوقت'
            )
        ]

    def clean(self):
        """
        التحقق من عدم وجود تعارض في جدول القاعات
        منع إنشاء مجموعتين في نفس القاعة + نفس اليوم + نفس الوقت
        """
        super().clean()

        if self.room and self.schedule_day and self.schedule_time:
            # البحث عن مجموعات أخرى في نفس القاعة + نفس اليوم + نفس الوقت
            conflicting_groups = Group.objects.filter(
                room=self.room,
                schedule_day=self.schedule_day,
                schedule_time=self.schedule_time,
                is_active=True
            ).exclude(pk=self.pk)

            if conflicting_groups.exists():
                conflict = conflicting_groups.first()
                raise ValidationError({
                    'room': f'تعارض في الجدول: القاعة "{self.room.name}" محجوزة لمجموعة "{conflict.group_name}" في نفس اليوم والوقت'
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
