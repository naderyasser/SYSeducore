# Generated migration for Payment Audit Log

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('payments', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('students', '0001_initial'),
        ('teachers', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentAuditLog',
            fields=[
                ('log_id', models.AutoField(primary_key=True, serialize=False)),
                ('action', models.CharField(
                    choices=[
                        ('payment_recorded', 'تسجيل دفع'),
                        ('credit_adjustment', 'تعديل ائتمان'),
                        ('fee_changed', 'تغيير سعر'),
                        ('status_changed', 'تغيير حالة'),
                        ('block_applied', 'تطبيق حظر'),
                        ('block_removed', 'إزالة حظر'),
                        ('bulk_payment', 'دفع جماعي'),
                    ],
                    max_length=20,
                    verbose_name='الإجراء'
                )),
                ('old_value', models.JSONField(
                    blank=True,
                    null=True,
                    verbose_name='القيمة القديمة'
                )),
                ('new_value', models.JSONField(
                    blank=True,
                    null=True,
                    verbose_name='القيمة الجديدة'
                )),
                ('amount', models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    max_digits=10,
                    null=True,
                    verbose_name='المبلغ'
                )),
                ('sessions_count', models.IntegerField(
                    blank=True,
                    null=True,
                    verbose_name='عدد الحصص'
                )),
                ('notes', models.TextField(
                    blank=True,
                    verbose_name='ملاحظات'
                )),
                ('ip_address', models.GenericIPAddressField(
                    blank=True,
                    null=True,
                    verbose_name='عنوان IP'
                )),
                ('created_at', models.DateTimeField(
                    auto_now_add=True,
                    verbose_name='التاريخ والوقت'
                )),
                ('group', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payment_audit_logs',
                    to='teachers.group',
                    verbose_name='المجموعة'
                )),
                ('performed_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='performed_payment_logs',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='تم بواسطة'
                )),
                ('student', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payment_audit_logs',
                    to='students.student',
                    verbose_name='الطالب'
                )),
            ],
            options={
                'verbose_name': 'سجل تدقيق مالي',
                'verbose_name_plural': 'سجلات التدقيق المالية',
                'db_table': 'payment_audit_logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='paymentauditlog',
            index=models.Index(
                fields=['student', 'created_at'],
                name='pay_audit_stu_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='paymentauditlog',
            index=models.Index(
                fields=['action', 'created_at'],
                name='pay_audit_act_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='paymentauditlog',
            index=models.Index(
                fields=['performed_by'],
                name='pay_audit_usr_idx'
            ),
        ),
    ]
