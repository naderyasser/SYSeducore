# Generated migration for strict attendance mode

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0001_initial'),
    ]

    operations = [
        # Update STATUS_CHOICES in Attendance model
        migrations.AlterField(
            model_name='attendance',
            name='status',
            field=models.CharField(
                choices=[
                    ('present', 'حاضر'),
                    ('late_blocked', 'ممنوع - تأخير'),
                    ('very_late', 'ممنوع - تأخير شديد'),
                    ('no_session', 'لا توجد حصة'),
                    ('blocked_payment', 'ممنوع - مصروفات'),
                    ('blocked_other', 'ممنوع'),
                ],
                max_length=20
            ),
        ),
        
        # Add new fields
        migrations.AddField(
            model_name='attendance',
            name='color_code',
            field=models.CharField(
                choices=[
                    ('green', 'green'),
                    ('red', 'red'),
                    ('yellow', 'yellow'),
                    ('white', 'white'),
                    ('gray', 'gray'),
                ],
                default='white',
                help_text='لون عرض الحالة على شاشة الكشك',
                max_length=20,
                verbose_name='كود اللون'
            ),
        ),
        
        migrations.AddField(
            model_name='attendance',
            name='allow_entry',
            field=models.BooleanField(
                default=False,
                help_text='هل يُسمح للطالب بالدخول أم لا',
                verbose_name='السماح بالدخول'
            ),
        ),
        
        migrations.AddField(
            model_name='attendance',
            name='minutes_late',
            field=models.IntegerField(
                default=0,
                help_text='عدد الدقائق المتأخرة (سالب للوصول المبكر)',
                verbose_name='دقائق التأخير'
            ),
        ),
        
        migrations.AddField(
            model_name='attendance',
            name='parent_notified',
            field=models.BooleanField(
                default=False,
                verbose_name='تم إخطار ولي الأمر'
            ),
        ),
        
        migrations.AddField(
            model_name='attendance',
            name='notification_sent_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='وقت إرسال الإخطار'
            ),
        ),
        
        migrations.AddField(
            model_name='attendance',
            name='notification_type',
            field=models.CharField(
                blank=True,
                max_length=20,
                verbose_name='نوع الإخطار'
            ),
        ),
        
        migrations.AddField(
            model_name='attendance',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        
        # Create BlockedAttempt model
        migrations.CreateModel(
            name='BlockedAttempt',
            fields=[
                ('attempt_id', models.AutoField(primary_key=True, serialize=False)),
                ('attempt_time', models.DateTimeField(default=django.utils.timezone.now, verbose_name='وقت المحاولة')),
                ('reason', models.CharField(
                    choices=[
                        ('late', 'تأخير'),
                        ('very_late', 'تأخير شديد'),
                        ('no_session', 'لا توجد حصة'),
                        ('payment', 'مصروفات'),
                        ('other', 'أخرى'),
                    ],
                    max_length=20,
                    verbose_name='سبب المنع'
                )),
                ('minutes_late', models.IntegerField(default=0, verbose_name='دقائق التأخير')),
                ('group_name', models.CharField(blank=True, max_length=100, verbose_name='اسم المجموعة')),
                ('scheduled_time', models.TimeField(blank=True, null=True, verbose_name='الوقت المجدول')),
                ('parent_notified', models.BooleanField(default=False, verbose_name='تم إخطار ولي الأمر')),
                ('notification_message', models.TextField(blank=True, verbose_name='رسالة الإخطار')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=models.deletion.CASCADE,
                    related_name='blocked_attempts',
                    to='attendance.session'
                )),
                ('student', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='blocked_attempts',
                    to='students.student'
                )),
            ],
            options={
                'verbose_name': 'محاولة دخول ممنوعة',
                'verbose_name_plural': 'محاولات الدخول الممنوعة',
                'db_table': 'blocked_attempts',
                'ordering': ['-attempt_time'],
                'indexes': [
                    models.Index(fields=['student', 'attempt_time'], name='block_att_student_idx'),
                    models.Index(fields=['reason'], name='block_att_reason_idx'),
                    models.Index(fields=['attempt_time'], name='block_att_time_idx'),
                ],
            },
        ),
        
        # Add indexes for Attendance model
        migrations.AddIndex(
            model_name='attendance',
            index=models.Index(
                fields=['status', 'allow_entry'],
                name='attend_status_entry_idx'
            ),
        ),
        
        migrations.AddIndex(
            model_name='attendance',
            index=models.Index(
                fields=['scan_time'],
                name='attend_scan_time_idx'
            ),
        ),
        
        migrations.AddIndex(
            model_name='attendance',
            index=models.Index(
                fields=['color_code'],
                name='attend_color_idx'
            ),
        ),
    ]
