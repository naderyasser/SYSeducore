# Generated migration for notification templates and preferences

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
        ('students', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        # Create NotificationTemplate model
        migrations.CreateModel(
            name='NotificationTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template_type', models.CharField(
                    choices=[
                        ('attendance_success', 'حضور ناجح ✅'),
                        ('late_block', 'منع تأخير 🔴'),
                        ('financial_block_new', 'منع مالي - طالب جديد 🟡'),
                        ('financial_block_debt', 'منع مالي - ديون 🟡'),
                        ('payment_reminder', 'تذكير بالدفع 📢'),
                        ('payment_confirmation', 'تأكيد استلام الدفع 🙏'),
                    ],
                    db_index=True,
                    max_length=50,
                    unique=True,
                    verbose_name='نوع القالب'
                )),
                ('template_name', models.CharField(max_length=200, verbose_name='اسم القالب')),
                ('content_arabic', models.TextField(verbose_name='المحتوى بالعربية')),
                ('content_english', models.TextField(blank=True, null=True, verbose_name='المحتوى بالإنجليزية')),
                ('available_variables', models.JSONField(
                    default=list,
                    help_text='قائمة المتغيرات التي يمكن استخدامها في القالب',
                    verbose_name='المتغيرات المتاحة'
                )),
                ('version', models.PositiveIntegerField(default=1, verbose_name='الإصدار')),
                ('is_active', models.BooleanField(default=True, verbose_name='نشط')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_templates',
                    to='accounts.user',
                    verbose_name='أنشأ بواسطة'
                )),
            ],
            options={
                'verbose_name': 'قالب إشعار',
                'verbose_name_plural': 'قوالب الإشعارات',
                'db_table': 'notification_templates',
                'ordering': ['template_type'],
            },
        ),
        
        # Create NotificationPreference model
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attendance_success_enabled', models.BooleanField(
                    default=True,
                    help_text='يمكن تعطيله',
                    verbose_name='إشعار الحضور الناجح'
                )),
                ('late_block_enabled', models.BooleanField(
                    default=True,
                    help_text='إلزامي - لا يمكن تعطيله',
                    verbose_name='إشعار منع التأخير'
                )),
                ('financial_block_enabled', models.BooleanField(
                    default=True,
                    help_text='إلزامي - لا يمكن تعطيله',
                    verbose_name='إشعار المنع المالي'
                )),
                ('payment_reminder_enabled', models.BooleanField(
                    default=True,
                    help_text='يمكن تعطيله',
                    verbose_name='تذكير الدفع اليومي'
                )),
                ('payment_confirmation_enabled', models.BooleanField(
                    default=True,
                    help_text='يمكن تعطيله',
                    verbose_name='تأكيد استلام الدفع'
                )),
                ('messages_last_hour', models.PositiveIntegerField(
                    default=0,
                    verbose_name='عدد الرسائل في آخر ساعة'
                )),
                ('last_message_time', models.DateTimeField(
                    blank=True,
                    null=True,
                    verbose_name='وقت آخر رسالة'
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
                ('student', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notification_preferences',
                    to='students.student',
                    verbose_name='الطالب'
                )),
            ],
            options={
                'verbose_name': 'تفضيلات الإشعارات',
                'verbose_name_plural': 'تفضيلات الإشعارات',
                'db_table': 'notification_preferences',
            },
        ),
        
        # Create NotificationCost model
        migrations.CreateModel(
            name='NotificationCost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.DateField(verbose_name='الشهر')),
                ('total_messages', models.PositiveIntegerField(default=0, verbose_name='عدد الرسائل')),
                ('total_cost', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='التكلفة الإجمالية')),
                ('cost_per_message', models.DecimalField(decimal_places=4, default=0.05, max_digits=5, verbose_name='تكلفة الرسالة')),
                ('currency', models.CharField(default='EGP', max_length=3, verbose_name='العملة')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='تاريخ التحديث')),
            ],
            options={
                'verbose_name': 'تكلفة الإشعارات',
                'verbose_name_plural': 'تكاليف الإشعارات',
                'db_table': 'notification_costs',
                'ordering': ['-month'],
            },
        ),
        
        # Update NotificationLog model with new fields
        migrations.AddField(
            model_name='notificationlog',
            name='template_used',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='logs',
                to='notifications.notificationtemplate',
                verbose_name='القالب المستخدم'
            ),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='api_message_id',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='معرف الرسالة من API'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='api_response',
            field=models.JSONField(blank=True, null=True, verbose_name='استجابة API'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='retry_count',
            field=models.PositiveIntegerField(default=0, verbose_name='عدد محاولات الإعادة'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='max_retries',
            field=models.PositiveIntegerField(default=3, verbose_name='أقصى محاولات'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='next_retry_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='موعد إعادة المحاولة القادم'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='error_code',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='رمز الخطأ'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='cost',
            field=models.DecimalField(decimal_places=4, default=0.05, max_digits=5, verbose_name='التكلفة'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='cost_recorded',
            field=models.BooleanField(default=False, verbose_name='تم تسجيل التكلفة'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='delivered_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='وقت التسليم'),
        ),
        migrations.AddField(
            model_name='notificationlog',
            name='context_data',
            field=models.JSONField(blank=True, null=True, verbose_name='بيانات السياق'),
        ),
        
        # Update STATUS_CHOICES
        migrations.AlterField(
            model_name='notificationlog',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'قيد الانتظار'),
                    ('sent', 'تم الإرسال'),
                    ('delivered', 'تم التسليم'),
                    ('failed', 'فشل'),
                    ('retrying', 'إعادة المحاولة'),
                ],
                db_index=True,
                default='pending',
                max_length=15,
                verbose_name='الحالة'
            ),
        ),
        
        # Update NOTIFICATION_TYPES
        migrations.AlterField(
            model_name='notificationlog',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('attendance_success', 'حضور ناجح'),
                    ('late_block', 'منع تأخير'),
                    ('financial_block_new', 'منع مالي - جديد'),
                    ('financial_block_debt', 'منع مالي - ديون'),
                    ('payment_reminder', 'تذكير دفع'),
                    ('payment_confirmation', 'تأكيد دفع'),
                    ('custom', 'مخصص'),
                ],
                db_index=True,
                max_length=30,
                verbose_name='نوع الإشعار'
            ),
        ),
        
        # Create indexes
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['status', 'created_at'], name='notif_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationlog',
            index=models.Index(fields=['notification_type', 'status'], name='notif_type_status_idx'),
        ),
        migrations.AddIndex(
            model_name='notificationcost',
            index=models.Index(fields=['month'], name='cost_month_idx'),
        ),
    ]
