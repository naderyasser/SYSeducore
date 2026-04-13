from django.db import models
from django.core.validators import RegexValidator
from django.conf import settings
import os
import io
import base64
import qrcode
from barcode import Code128
from barcode.writer import ImageWriter
from PIL import Image
from apps.core.models import SoftDeleteModel


class Student(SoftDeleteModel):
    """
    Student model for managing students.
    الطالب يمكنه الانتساب لأكثر من مجموعة (أكثر من مدرس)
    ملف الطالب الشامل مع بيانات إضافية
    """

    GENDER_CHOICES = [
        ('male', 'ذكر'),
        ('female', 'أنثى'),
    ]

    EDUCATION_STAGE_CHOICES = [
        ('primary', 'ابتدائي'),
        ('preparatory', 'إعدادي'),
        ('secondary', 'ثانوي'),
    ]

    EDUCATION_YEAR_CHOICES = [
        ('1', 'الأول'),
        ('2', 'الثاني'),
        ('3', 'الثالث'),
        ('4', 'الرابع'),
        ('5', 'الخامس'),
        ('6', 'السادس'),
    ]

    EDUCATION_TYPE_CHOICES = [
        ('general', 'عام'),
        ('languages', 'لغات'),
        ('experimental', 'تجريبي'),
    ]

    student_id = models.AutoField(primary_key=True)
    student_code = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        verbose_name="كود الطالب",
        help_text="كود قصير ومميز (مثال: 1001، 5050)"
    )
    full_name = models.CharField(max_length=255, verbose_name="الاسم الكامل")

    # Gender - النوع
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        default='male',
        verbose_name="النوع",
        help_text="لتحديد نوع المجموعة المناسبة"
    )

    # Education info - المرحلة الدراسية
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
    education_type = models.CharField(
        max_length=20,
        choices=EDUCATION_TYPE_CHOICES,
        default='general',
        verbose_name="نوع التعليم"
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

    # Student phone - رقم الطالب (إجباري)
    student_phone = models.CharField(
        validators=[RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="رقم الهاتف يجب أن يكون بالصيغة: '+999999999'"
        )],
        max_length=17,
        blank=True,
        verbose_name="رقم الطالب"
    )

    # Parent phone - رقم ولي الأمر (إجباري)
    parent_phone = models.CharField(
        validators=[RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="رقم الهاتف يجب أن يكون بالصيغة: '+999999999'"
        )],
        max_length=17,
        verbose_name="هاتف ولي الأمر",
        help_text="للأولاد = الأب، للبنات = الأم/الأخت"
    )

    # Additional student information
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ الميلاد"
    )
    school_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="اسم المدرسة"
    )
    address = models.TextField(
        blank=True,
        verbose_name="العنوان"
    )
    parent_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="اسم ولي الأمر"
    )

    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    # Subscription fields - حقول الاشتراك
    last_payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ آخر دفع",
        help_text="تاريخ تفعيل آخر اشتراك"
    )
    subscription_expiry_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاريخ انتهاء الاشتراك",
        help_text="تاريخ انتهاء صلاحية الاشتراك (30 يوم من التفعيل)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'students'
        verbose_name = 'طالب'
        verbose_name_plural = 'الطلاب'
        ordering = ['-created_at']

    def __str__(self):
        return self.full_name

    def get_education_display_full(self):
        """عرض المرحلة الدراسية كاملة"""
        parts = []
        if self.education_stage:
            parts.append(self.get_education_stage_display())
        if self.education_year:
            parts.append(self.get_education_year_display())
        if self.education_type and self.education_type != 'general':
            parts.append(self.get_education_type_display())
        return " - ".join(parts) if parts else "-"

    def get_parent_label(self):
        """تحديد تسمية ولي الأمر بناءً على النوع"""
        if self.gender == 'male':
            return "رقم الأب"
        return "رقم الأم/الأخت"

    def clean(self):
        super().clean()
        STAGE_YEAR_MAP = {
            'primary': ['1', '2', '3', '4', '5', '6'],
            'preparatory': ['1', '2', '3'],
            'secondary': ['1', '2', '3'],
        }
        if self.education_stage and self.education_year:
            valid_years = STAGE_YEAR_MAP.get(self.education_stage, [])
            if self.education_year not in valid_years:
                from django.core.exceptions import ValidationError
                stage_display = dict(self.EDUCATION_STAGE_CHOICES).get(self.education_stage, self.education_stage)
                raise ValidationError({
                    'education_year': f'الصف {self.education_year} غير متاح للمرحلة {stage_display}'
                })

    def save(self, *args, **kwargs):
        """Auto-generate student code if not provided"""
        if not self.student_code:
            self.student_code = self.generate_next_code()
        super().save(*args, **kwargs)

    @classmethod
    def generate_next_code(cls):
        """توليد الكود التالي (آخر كود رقمي + 1)، يبدأ من 1001 - مع حماية من التزامن"""
        from django.db import transaction
        from django.db.models import Max
        from django.db.models.functions import Cast
        from django.db.models import IntegerField

        with transaction.atomic():
            # Lock all numeric-code rows to prevent concurrent duplicate generation
            locked_qs = cls.all_objects.select_for_update().filter(
                student_code__regex=r'^\d+$'
            )
            last_numeric = locked_qs.annotate(
                code_int=Cast('student_code', IntegerField())
            ).aggregate(max_code=Max('code_int'))

            last_code = last_numeric.get('max_code')
            return str(last_code + 1) if last_code else '1001'

    def generate_qr_image(self):
        """Generate QR code image for student"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=3,
        )
        qr.add_data(self.student_code)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").convert('RGB')

    def generate_barcode_image(self):
        """Generate Code128 barcode image for student (primary)"""
        buffer = io.BytesIO()
        code128 = Code128(self.student_code, writer=ImageWriter())
        code128.write(buffer, options={
            'module_height': 15,
            'module_width': 0.6,
            'quiet_zone': 2,
            'font_size': 1,
            'text_distance': 1,
            'dpi': 300,
            'background': 'white',
            'foreground': 'black',
            'write_text': False,
        })
        buffer.seek(0)
        return Image.open(buffer)

    def get_barcode_base64(self):
        """Get Code128 barcode as base64 string"""
        try:
            img = self.generate_barcode_image()
            if img.mode != 'RGB':
                img = img.convert('RGB')
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            return base64.b64encode(buffer.getvalue()).decode()
        except Exception:
            return ''

    def save_barcode_image(self):
        """Save Code128 barcode image to media directory"""
        barcode_dir = os.path.join(settings.MEDIA_ROOT, 'barcodes')
        os.makedirs(barcode_dir, exist_ok=True)

        filepath = os.path.join(barcode_dir, f'{self.student_code}.png')
        img = self.generate_barcode_image()
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(filepath)
        return filepath

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
    
    def is_subscription_active(self):
        """التحقق من صلاحية الاشتراك"""
        from django.utils import timezone
        if not self.subscription_expiry_date:
            return False
        return timezone.now().date() <= self.subscription_expiry_date
    
    def activate_subscription(self, days=30):
        """تفعيل اشتراك الطالب لمدة محددة (افتراضي 30 يوم)"""
        from django.utils import timezone
        from datetime import timedelta
        
        today = timezone.now().date()
        self.last_payment_date = today
        self.subscription_expiry_date = today + timedelta(days=days)
        self.is_active = True
        self.save()
        
        return self.subscription_expiry_date
    
    def get_subscription_status(self):
        """الحصول على حالة الاشتراك"""
        from django.utils import timezone
        
        if not self.subscription_expiry_date:
            return {
                'status': 'inactive',
                'message': 'لم يتم تفعيل الاشتراك',
                'days_remaining': 0
            }
        
        today = timezone.now().date()
        days_remaining = (self.subscription_expiry_date - today).days
        
        if days_remaining < 0:
            return {
                'status': 'expired',
                'message': f'منتهي منذ {abs(days_remaining)} يوم',
                'days_remaining': days_remaining
            }
        elif days_remaining == 0:
            return {
                'status': 'expires_today',
                'message': 'ينتهي اليوم',
                'days_remaining': 0
            }
        elif days_remaining <= 3:
            return {
                'status': 'expiring_soon',
                'message': f'ينتهي خلال {days_remaining} يوم',
                'days_remaining': days_remaining
            }
        else:
            return {
                'status': 'active',
                'message': f'نشط - متبقي {days_remaining} يوم',
                'days_remaining': days_remaining
            }

    def get_active_groups_count(self):
        """Get count of active group enrollments"""
        return StudentGroupEnrollment.objects.filter(
            student=self,
            is_active=True
        ).count()

    def get_total_paid_amount(self):
        """Get total amount paid by student"""
        from apps.payments.models import Payment
        total = Payment.objects.filter(
            student=self,
            status='paid'
        ).aggregate(total=models.Sum('amount_paid'))['total']
        return total or 0


class StudentGroupEnrollment(models.Model):
    """
    نموذج وسيط لربط الطالب بالمجموعة مع معلومات إضافية
    يسمح بتحديد الحالة المالية لكل مجموعة على حدة
    """
    FINANCIAL_STATUS_CHOICES = [
        ('normal', 'عادي'),
        ('symbolic', 'مبلغ رمزي'),
        ('exempt', 'إعفاء كامل'),
        ('per_session', 'دفع بالحصة'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        verbose_name="الطالب",
        related_name='group_enrollments'
    )
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.PROTECT,
        verbose_name="المجموعة"
    )

    financial_status = models.CharField(
        max_length=15,
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

    def get_financial_status_display_with_amount(self):
        """Get financial status display with amount if symbolic"""
        status = self.get_financial_status_display()
        if self.financial_status == 'symbolic' and self.custom_fee:
            return f"{status} ({self.custom_fee} ج.م)"
        return status
