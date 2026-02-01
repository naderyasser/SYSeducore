# Generated migration for room scheduling system

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('teachers', '0001_initial'),
    ]

    operations = [
        # Add session_duration field to Group model
        migrations.AddField(
            model_name='group',
            name='session_duration',
            field=models.PositiveIntegerField(
                choices=[(60, 'ساعة واحدة'), (90, 'ساعة ونصف'), (120, 'ساعتان'), (150, 'ساعة ونصف ونصف'), (180, '3 ساعات')],
                default=120,
                verbose_name='مدة الحصة (دقيقة)',
                help_text='مدة الحصة بالدقائق، تُستخدم للكشف عن التعارضات الزمنية'
            ),
        ),
        
        # Add updated_at field to Group model
        migrations.AddField(
            model_name='group',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        
        # Remove old UniqueConstraint (replaced by more sophisticated conflict detection)
        migrations.RemoveConstraint(
            model_name='group',
            name='unique_room_schedule',
        ),
        
        # Add database indexes for optimized queries
        migrations.AddIndex(
            model_name='group',
            index=models.Index(fields=['room', 'schedule_day', 'schedule_time'], name='group_room_schedule_idx'),
        ),
        
        migrations.AddIndex(
            model_name='group',
            index=models.Index(fields=['schedule_day', 'schedule_time'], name='group_day_time_idx'),
        ),
        
        migrations.AddIndex(
            model_name='group',
            index=models.Index(fields=['is_active'], name='group_is_active_idx'),
        ),
    ]
