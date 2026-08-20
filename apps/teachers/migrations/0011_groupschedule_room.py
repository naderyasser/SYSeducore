# Generated manually (not via makemigrations) — split from the room decoupling
# into two migrations on purpose. This one only ADDS GroupSchedule.room and
# backfills it from each row's group's (still-present) room. Group.room is
# removed separately in 0012, once this step is confirmed safe on real data.

import django.db.models.deletion
from django.db import migrations, models


def backfill_schedule_room(apps, schema_editor):
    """Copy each GroupSchedule row's room from its owning group's current room."""
    GroupSchedule = apps.get_model('teachers', 'GroupSchedule')
    for schedule in GroupSchedule.objects.select_related('group').all():
        if schedule.group.room_id != schedule.room_id:
            schedule.room_id = schedule.group.room_id
            schedule.save(update_fields=['room'])


def reverse_backfill(apps, schema_editor):
    """Reverse: nothing to do, Group.room still exists and is unchanged."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('teachers', '0010_subject_deleted_at_subject_deleted_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupschedule',
            name='room',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='schedule_entries', to='teachers.room',
                verbose_name='القاعة',
            ),
        ),
        migrations.RunPython(backfill_schedule_room, reverse_backfill),
    ]
