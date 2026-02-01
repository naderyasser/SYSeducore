# Generated migration for QR code fields

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('students', '0002_add_credit_system_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='qr_code_base64',
            field=models.TextField(blank=True, help_text='رمز QR مشفر بصيغة base64 للطباعة', null=True, verbose_name='رمز الاستجابة السريعة (QR)'),
        ),
        migrations.AddField(
            model_name='student',
            name='qr_code_generated_at',
            field=models.DateTimeField(blank=True, help_text='تاريخ آخر توليد لرمز QR', null=True, verbose_name='تاريخ توليد QR'),
        ),
    ]
