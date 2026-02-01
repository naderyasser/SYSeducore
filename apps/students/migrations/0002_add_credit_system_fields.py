# Generated migration for Credit System

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('students', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='studentgroupenrollment',
            name='is_new_student',
            field=models.BooleanField(
                default=True,
                help_text='الطلاب الجدد يجب أن يدفعوا قبل أول حصة',
                verbose_name='طالب جديد'
            ),
        ),
        migrations.AddField(
            model_name='studentgroupenrollment',
            name='credit_balance',
            field=models.IntegerField(
                default=0,
                help_text='عدد الحصص المسموح بها بدون دفع (0 للجدد، 2 للقدامى)',
                verbose_name='رصيد الائتمان (حصص)'
            ),
        ),
        migrations.AddField(
            model_name='studentgroupenrollment',
            name='sessions_attended',
            field=models.IntegerField(
                default=0,
                help_text='عدد الحصص التي حضرها الطالب',
                verbose_name='الحصص المحضور'
            ),
        ),
        migrations.AddField(
            model_name='studentgroupenrollment',
            name='sessions_paid_for',
            field=models.IntegerField(
                default=0,
                help_text='عدد الحصص التي تم دفعها',
                verbose_name='الحصص المدفوعة'
            ),
        ),
        migrations.AddField(
            model_name='studentgroupenrollment',
            name='last_payment_date',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='تاريخ آخر دفع'
            ),
        ),
        migrations.AddField(
            model_name='studentgroupenrollment',
            name='last_payment_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='مبلغ آخر دفع'
            ),
        ),
        migrations.AddField(
            model_name='studentgroupenrollment',
            name='is_financially_blocked',
            field=models.BooleanField(
                default=False,
                help_text='تم حظر الطالب بسبب عدم دفع المصروفات',
                verbose_name='محظور مالياً'
            ),
        ),
        migrations.AddField(
            model_name='studentgroupenrollment',
            name='financial_block_reason',
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name='سبب الحظر المالي'
            ),
        ),
        migrations.AddIndex(
            model_name='studentgroupenrollment',
            index=models.Index(
                fields=['is_new_student', 'credit_balance'],
                name='stu_cred_idx'
            ),
        ),
        migrations.AddIndex(
            model_name='studentgroupenrollment',
            index=models.Index(
                fields=['is_financially_blocked'],
                name='stu_fin_block_idx'
            ),
        ),
    ]
