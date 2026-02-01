from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class PaymentAuditLog(models.Model):
    """
    سجل تدقيق لجميع التغييرات المالية
    Audit log for tracking all financial changes
    """
    ACTION_CHOICES = [
        ('payment_recorded', 'تسجيل دفع'),
        ('credit_adjustment', 'تعديل ائتمان'),
        ('fee_changed', 'تغيير سعر'),
        ('status_changed', 'تغيير حالة'),
        ('block_applied', 'تطبيق حظر'),
        ('block_removed', 'إزالة حظر'),
        ('bulk_payment', 'دفع جماعي'),
    ]

    log_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='payment_audit_logs',
        verbose_name="الطالب"
    )
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.CASCADE,
        related_name='payment_audit_logs',
        verbose_name="المجموعة",
        null=True,
        blank=True
    )
    
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name="الإجراء"
    )
    
    # القيم القديمة والجديدة
    old_value = models.JSONField(
        null=True,
        blank=True,
        verbose_name="القيمة القديمة"
    )
    new_value = models.JSONField(
        null=True,
        blank=True,
        verbose_name="القيمة الجديدة"
    )
    
    # تفاصيل إضافية
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="المبلغ"
    )
    sessions_count = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="عدد الحصص"
    )
    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات"
    )
    
    # من قام بالتغيير
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='performed_payment_logs',
        verbose_name="تم بواسطة"
    )
    
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="عنوان IP"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="التاريخ والوقت"
    )

    class Meta:
        db_table = 'payment_audit_logs'
        verbose_name = 'سجل تدقيق مالي'
        verbose_name_plural = 'سجلات التدقيق المالية'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'created_at']),
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['performed_by']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.student.full_name} - {self.created_at}"


class Payment(models.Model):
    """
    Payment model for managing student payments.
    الطالب الآن يمكن أن يكون لديه مدفوعات متعددة لمجموعات مختلفة في نفس الشهر
    """
    STATUS_CHOICES = [
        ('paid', 'مدفوع'),
        ('partial', 'مدفوع جزئياً'),
        ('unpaid', 'غير مدفوع'),
    ]

    payment_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='payments'
    )
    group = models.ForeignKey(
        'teachers.Group',
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name="المجموعة"
    )

    month = models.DateField(verbose_name="الشهر")
    amount_due = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="المبلغ المطلوب"
    )
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="المبلغ المدفوع"
    )

    payment_date = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الدفع")
    sessions_attended = models.IntegerField(default=0, verbose_name="عدد الحصص")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='unpaid',
        verbose_name="الحالة"
    )

    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        unique_together = ['student', 'group', 'month']
        ordering = ['-month']

    def __str__(self):
        return f"{self.student.full_name} - {self.group.group_name} - {self.month.strftime('%Y-%m')}"

    @property
    def remaining(self):
        """Calculate remaining amount to be paid."""
        return max(0, self.amount_due - self.amount_paid)
