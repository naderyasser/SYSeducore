# Removes Group.room now that every GroupSchedule row carries its own room
# (backfilled in 0011). A room is a property of a session, not the group —
# two days of the same group may meet in two different rooms.
#
# Reversing this migration re-adds the column, but empty: the per-day values
# now live in GroupSchedule.room and may have diverged since 0011 ran, so
# there is no single "the group's room" left to restore.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teachers', '0011_groupschedule_room'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='group',
            name='room',
        ),
    ]
