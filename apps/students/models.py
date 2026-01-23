from django.db import models
from django.core.validators import RegexValidator


class Student(models.Model):
    """
    Student model for managing students.
    """
    FINANCIAL_STATUS_CHOICES = [
        ('normal', 'عادي'),
        ('symbolic', 'مبلغ رمزي'),
        ('exempt', 'إعفاء كامل'),
    ]
    
    student_id = models.AutoField(primary_key=True)
    barcode = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="كود الباركود"
    )
    full_name = models.CharField(max_length=255, verbose_name="الاسم الكامل")
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.PROTECT,
        related_name='students',
        verbose_name="المجموعة"
    )
    
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="رقم الهاتف يجب أن يكون بالصيغة: '+999999999'"
    )
    parent_phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        verbose_name="هاتف ولي الأمر"
    )
    
    financial_status = models.CharField(
        max_length=10,
        choices=FINANCIAL_STATUS_CHOICES,
        default='normal',
        verbose_name="الحالة المالية"
    )
    custom_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="المبلغ المخصص"
    )
    
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'students'
        verbose_name = 'طالب'
        verbose_name_plural = 'الطلاب'
        ordering = ['full_name']
    
    def __str__(self):
        return self.full_name
    
    def get_monthly_fee(self):
        """احسب المصروفات الشهرية حسب الحالة المالية"""
        if self.financial_status == 'exempt':
            return 0
        elif self.financial_status == 'symbolic':
            return self.custom_fee or 0
        else:
            return self.group.standard_fee
