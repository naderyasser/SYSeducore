from django.db import models
from django.contrib.auth import get_user_model
from apps.students.models import Student
from apps.teachers.models import Group

User = get_user_model()


class WhatsAppMessage(models.Model):
    """
    نموذج لتتبع رسائل الواتساب المرسلة
    """
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('sent', 'تم الإرسال'),
        ('failed', 'فشل الإرسال'),
        ('delivered', 'تم التسليم'),
    ]

    MESSAGE_TYPE_CHOICES = [
        ('student', 'رسالة للطالب'),
        ('parent', 'رسالة لولي الأمر'),
        ('group', 'رسالة جماعية'),
        ('attendance', 'تقرير الحضور'),
        ('payment', 'تقرير المدفوعات'),
        ('custom', 'رسالة مخصصة'),
    ]

    message_id = models.AutoField(primary_key=True)
    
    # البيانات الأساسية
    phone_number = models.CharField(max_length=20, verbose_name="رقم الهاتف")
    message_text = models.TextField(verbose_name="نص الرسالة")
    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPE_CHOICES,
        default='custom',
        verbose_name="نوع الرسالة"
    )
    
    # الارتباطات
    student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_messages',
        verbose_name="الطالب"
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_messages',
        verbose_name="المجموعة"
    )
    sent_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_messages_sent',
        verbose_name="المُرسِل"
    )
    
    # الحالة والتوقيت
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="حالة الرسالة"
    )
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الإرسال")
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التسليم")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")
    
    # ملاحظات
    error_message = models.TextField(blank=True, verbose_name="رسالة الخطأ")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        db_table = 'whatsapp_messages'
        verbose_name = 'رسالة واتساب'
        verbose_name_plural = 'رسائل واتساب'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['phone_number', '-created_at']),
            models.Index(fields=['message_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.message_type}"


class WhatsAppTemplate(models.Model):
    """
    قوالب رسائل الواتساب المعرّفة مسبقاً
    """
    template_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, verbose_name="اسم القالب")
    description = models.TextField(blank=True, verbose_name="الوصف")
    message_text = models.TextField(verbose_name="نص الرسالة")
    
    # الاستخدام
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'whatsapp_templates'
        verbose_name = 'قالب واتساب'
        verbose_name_plural = 'قوالب واتساب'
        ordering = ['name']

    def __str__(self):
        return self.name
