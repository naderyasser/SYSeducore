from django.db import models
from django.core.validators import RegexValidator


class Student(models.Model):
    """
    Student model for managing students.
    الطالب يمكنه الانتساب لأكثر من مجموعة (أكثر من مدرس)
    """

    student_id = models.AutoField(primary_key=True)
    student_code = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        verbose_name="كود الطالب",
        help_text="كود قصير ومميز (مثال: 1001، 5050)"
    )
    full_name = models.CharField(max_length=255, verbose_name="الاسم الكامل")
    
    # QR Code fields
    qr_code_base64 = models.TextField(
        blank=True,
        null=True,
        verbose_name="رمز الاستجابة السريعة (QR)",
        help_text="رمز QR مشفر بصيغة base64 للطباعة"
    )
    qr_code_generated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ توليد QR",
        help_text="تاريخ آخر توليد لرمز QR"
    )
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
    
    # ========================================
    # QR Code Methods
    # ========================================
    
    def generate_qr_code(self):
        """
        Generate QR code for this student
        """
        from .utils import QRCodeGenerator
        from django.utils import timezone
        
        self.qr_code_base64 = QRCodeGenerator.generate_qr_for_student(self)
        self.qr_code_generated_at = timezone.now()
        self.save(update_fields=['qr_code_base64', 'qr_code_generated_at'])
        return self.qr_code_base64
    
    def get_qr_code(self):
        """
        Get QR code, generating if not exists
        """
        if not self.qr_code_base64:
            self.generate_qr_code()
        return self.qr_code_base64
    
    def regenerate_qr_code(self):
        """
        Force regenerate QR code (e.g., if student_code changed)
        """
        return self.generate_qr_code()
    
    def has_qr_code(self):
        """
        Check if student has QR code generated
        """
        return bool(self.qr_code_base64)


class StudentGroupEnrollment(models.Model):
    """
    نموذج وسيط لربط الطالب بالمجموعة مع معلومات إضافية
    يسمح بتحديد الحالة المالية لكل مجموعة على حدة
    
    نظام الائتمان الجديد:
    - الطلاب الجدد: credit_balance = 0 (يجب الدفع قبل أول حصة)
    - الطلاب القدامى: credit_balance = 2 (فترة سماح لحصتين)
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

    # ========================================
    # حقول نظام الائتمان (Credit System)
    # ========================================
    is_new_student = models.BooleanField(
        default=True,
        verbose_name="طالب جديد",
        help_text="الطلاب الجدد يجب أن يدفعوا قبل أول حصة"
    )
    credit_balance = models.IntegerField(
        default=0,
        verbose_name="رصيد الائتمان (حصص)",
        help_text="عدد الحصص المسموح بها بدون دفع (0 للجدد، 2 للقدامى)"
    )
    sessions_attended = models.IntegerField(
        default=0,
        verbose_name="الحصص المحضور",
        help_text="عدد الحصص التي حضرها الطالب"
    )
    sessions_paid_for = models.IntegerField(
        default=0,
        verbose_name="الحصص المدفوعة",
        help_text="عدد الحصص التي تم دفعها"
    )
    last_payment_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ آخر دفع"
    )
    last_payment_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="مبلغ آخر دفع"
    )
    is_financially_blocked = models.BooleanField(
        default=False,
        verbose_name="محظور مالياً",
        help_text="تم حظر الطالب بسبب عدم دفع المصروفات"
    )
    financial_block_reason = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="سبب الحظر المالي"
    )

    enrolled_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الانضمام")
    is_active = models.BooleanField(default=True, verbose_name="نشط")

    class Meta:
        db_table = 'student_group_enrollments'
        unique_together = ['student', 'group']
        verbose_name = 'تسجيل طالب في مجموعة'
        verbose_name_plural = 'تسجيلات الطلاب في المجموعات'
        indexes = [
            models.Index(fields=['is_new_student', 'credit_balance']),
            models.Index(fields=['is_financially_blocked']),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.group.group_name}"

    def get_effective_fee(self):
        """
        الحصول على المبلغ الفعلي الذي يجب دفعه
        يأخذ في الاعتبار custom_fee و group.standard_fee
        """
        if self.financial_status == 'exempt':
            return 0
        elif self.financial_status == 'symbolic':
            return self.custom_fee or 0
        else:
            return self.custom_fee or self.group.standard_fee

    def get_credit_status(self):
        """
        الحصول على حالة الائتمان للطالب
        Returns: dict with status details
        """
        debt = self.sessions_attended - self.sessions_paid_for
        remaining_credit = self.credit_balance - debt
        
        return {
            'is_new_student': self.is_new_student,
            'credit_balance': self.credit_balance,
            'sessions_attended': self.sessions_attended,
            'sessions_paid_for': self.sessions_paid_for,
            'debt': debt,
            'remaining_credit': remaining_credit,
            'is_blocked': self.is_financially_blocked,
            'block_reason': self.financial_block_reason,
        }

    def can_attend_session(self):
        """
        التحقق من إمكانية حضور الطالب للحصة
        Returns: dict with allowed status and reason
        """
        # الإعفاء الكامل = مسموح دائماً
        if self.financial_status == 'exempt':
            return {
                'allowed': True,
                'reason': 'exempt',
                'message': ''
            }

        # طالب جديد بدون دفع = ممنوع
        if self.is_new_student and self.sessions_paid_for == 0:
            return {
                'allowed': False,
                'reason': 'new_student_no_payment',
                'message': '⛔ ممنوع الدخول - يرجى تسجيل المصروفات أولاً'
            }

        # حساب الدين
        debt = self.sessions_attended - self.sessions_paid_for
        remaining_credit = self.credit_balance - debt

        # تجاوز الحد المسموح = ممنوع
        if remaining_credit < 0:
            return {
                'allowed': False,
                'reason': 'credit_exceeded',
                'message': f'⛔ ممنوع الدخول - لديك {debt} حصة غير مدفوعة'
            }

        # مسموح
        return {
            'allowed': True,
            'reason': 'ok',
            'message': ''
        }
