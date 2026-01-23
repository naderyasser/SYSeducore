from django.db import models


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
    
    schedule_day = models.CharField(
        max_length=10,
        choices=DAYS_CHOICES,
        verbose_name="يوم الحصة"
    )
    schedule_time = models.TimeField(verbose_name="وقت الحصة")
    grace_period = models.IntegerField(
        default=10,
        verbose_name="وقت السماح (بالدقائق)"
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
    
    def __str__(self):
        return f"{self.group_name} - {self.teacher.full_name}"
