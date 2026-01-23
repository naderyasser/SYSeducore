from django.db import models
from django.core.validators import RegexValidator


class Student(models.Model):
    """
    Student model for managing students.
    الطالب يمكنه الانتساب لأكثر من مجموعة (أكثر من مدرس)
    """

    student_id = models.AutoField(primary_key=True)
    barcode = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="كود الباركود"
    )
    full_name = models.CharField(max_length=255, verbose_name="الاسم الكامل")
    groups = models.ManyToManyField(
        'teachers.Group',
        through='StudentGroupEnrollment',
        related_name='enrolled_students',
        verbose_name="المجموعات"
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

    def get_monthly_fee_for_group(self, group):
        """احسب المصروفات الشهرية لمجموعة معينة حسب الحالة المالية"""
        try:
            enrollment = StudentGroupEnrollment.objects.get(
                student=self,
                group=group
            )
            if enrollment.financial_status == 'exempt':
                return 0
            elif enrollment.financial_status == 'symbolic':
                return enrollment.custom_fee or 0
            else:
                return group.standard_fee
        except StudentGroupEnrollment.DoesNotExist:
            return 0


class StudentGroupEnrollment(models.Model):
    """
    نموذج وسيط لربط الطالب بالمجموعة مع معلومات إضافية
    يسمح بتحديد الحالة المالية لكل مجموعة على حدة
    """
    FINANCIAL_STATUS_CHOICES = [
        ('normal', 'عادي'),
        ('symbolic', 'مبلغ رمزي'),
        ('exempt', 'إعفاء كامل'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        verbose_name="الطالب"
    )
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.CASCADE,
        verbose_name="المجموعة"
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

    enrolled_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الانضمام")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        db_table = 'student_group_enrollments'
        unique_together = ['student', 'group']
        verbose_name = 'تسجيل طالب في مجموعة'
        verbose_name_plural = 'تسجيلات الطلاب في المجموعات'

    def __str__(self):
        return f"{self.student.full_name} - {self.group.group_name}"
