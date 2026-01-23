from django.db import models


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
