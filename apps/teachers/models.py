from django.db import models
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta


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


class Subject(models.Model):
    """
    Subject model for managing subjects/specializations.
    موديل المواد الدراسية
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="اسم المادة")

    class Meta:
        db_table = 'subjects'
        verbose_name = 'مادة دراسية'
        verbose_name_plural = 'المواد الدراسية'
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
    email = models.EmailField(
        blank=True,
        null=True,
        unique=True,
        verbose_name="البريد الإلكتروني",
        help_text="حقل اختياري"
    )

    # Multi-select subjects through M2M
    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name='teachers',
        verbose_name="التخصصات / المواد"
    )
    # Keep legacy field for backward compat (will be migrated)
    specialization = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="التخصص (قديم)"
    )

    # Profile photo - required for student card back
    photo = models.ImageField(
        upload_to='teachers/photos/',
        blank=True,
        null=True,
        verbose_name="الصورة الشخصية",
        help_text="ضرورية لطباعة ظهر كارنيه الطالب"
    )

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

    def get_subjects_display(self):
        """عرض المواد مفصولة بفاصلة"""
        subjects = self.subjects.all()
        if subjects:
            return " ، ".join([s.name for s in subjects])
        return self.specialization or "-"


class Group(models.Model):
    """
    Group model for managing student groups.
    يدعم مدة الحصة + منع التعارض الذكي (تداخل الوقت) + تصنيف الجنس والمرحلة
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

    GENDER_CHOICES = [
        ('male', 'بنين فقط'),
        ('female', 'بنات فقط'),
        ('mixed', 'مختلط'),
    ]

    EDUCATION_STAGE_CHOICES = [
        ('primary', 'ابتدائي'),
        ('preparatory', 'إعدادي'),
        ('secondary', 'ثانوي'),
    ]

    EDUCATION_YEAR_CHOICES = [
        ('1', 'أولى'),
        ('2', 'ثانية'),
        ('3', 'ثالثة'),
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
    schedule_time = models.TimeField(verbose_name="وقت بداية الحصة")

    # Duration field - مدة الحصة بالدقائق
    duration_minutes = models.PositiveIntegerField(
        default=120,
        verbose_name="مدة الحصة (بالدقائق)",
        help_text="مدة الحصة بالدقائق (مثال: 120 = ساعتين)"
    )

    # Gender classification - تصنيف الجنس
    gender_type = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        default='mixed',
        verbose_name="نوع المجموعة (الجنس)"
    )

    # Education stage and year - المرحلة والسنة الدراسية
    education_stage = models.CharField(
        max_length=20,
        choices=EDUCATION_STAGE_CHOICES,
        blank=True,
        verbose_name="المرحلة الدراسية"
    )
    education_year = models.CharField(
        max_length=5,
        choices=EDUCATION_YEAR_CHOICES,
        blank=True,
        verbose_name="السنة الدراسية"
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

    class Meta:
        db_table = 'groups'
        verbose_name = 'مجموعة'
        verbose_name_plural = 'المجموعات'
        # Remove old unique constraint - replaced by smart overlap check

    def get_end_time(self):
        """حساب وقت نهاية الحصة بناءً على وقت البداية والمدة"""
        start_dt = datetime.combine(datetime.today(), self.schedule_time)
        end_dt = start_dt + timedelta(minutes=self.duration_minutes)
        return end_dt.time()

    def clean(self):
        """
        التحقق من عدم وجود تداخل في جدول القاعات (Smart Overlap Check)
        يسمح بنفس القاعة لمدرسين مختلفين بشرط عدم تداخل التوقيت

        المنطق: إذا حجز مدرس القاعة من 11:00 إلى 1:00،
        يمكن لمدرس آخر الحجز فيها بدءاً من 1:00،
        ولكن يمنع الحجز الساعة 12:00
        """
        super().clean()

        if self.room and self.schedule_day and self.schedule_time:
            # حساب أوقات البداية والنهاية لهذه المجموعة
            new_start = datetime.combine(datetime.today(), self.schedule_time)
            new_end = new_start + timedelta(minutes=self.duration_minutes)

            # البحث عن مجموعات أخرى في نفس القاعة + نفس اليوم
            other_groups = Group.objects.filter(
                room=self.room,
                schedule_day=self.schedule_day,
                is_active=True
            ).exclude(pk=self.pk)

            for other in other_groups:
                # حساب أوقات المجموعة الأخرى
                other_start = datetime.combine(datetime.today(), other.schedule_time)
                other_end = other_start + timedelta(minutes=other.duration_minutes)

                # التحقق من التداخل: start1 < end2 AND start2 < end1
                if new_start < other_end and other_start < new_end:
                    raise ValidationError({
                        'schedule_time': (
                            f'تعارض في الجدول: القاعة "{self.room.name}" محجوزة لمجموعة '
                            f'"{other.group_name}" من {other.schedule_time.strftime("%I:%M %p")} '
                            f'إلى {other.get_end_time().strftime("%I:%M %p")}. '
                            f'يمكنك الحجز بدءاً من {other.get_end_time().strftime("%I:%M %p")}'
                        )
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

    def get_duration_display(self):
        """عرض المدة بشكل مقروء"""
        hours = self.duration_minutes // 60
        mins = self.duration_minutes % 60
        if hours and mins:
            return f"{hours} ساعة و {mins} دقيقة"
        elif hours:
            return f"{hours} ساعة" if hours == 1 else f"{hours} ساعات"
        else:
            return f"{mins} دقيقة"
