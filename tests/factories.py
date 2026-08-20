"""
Shared test helpers for creating a :class:`~apps.teachers.models.Group`
together with its schedule.

Before the room-decoupling migration, ``Group.objects.create(room=room,
schedule_day=day, schedule_time=time, ...)`` was enough — a group had one
room applied to every session. Now a room belongs to the *session*
(``GroupSchedule.room``), so a bare ``Group.objects.create()`` no longer
creates any schedule row at all. ``create_group_with_schedule`` is the
mechanical drop-in replacement for that old pattern: same call shape, but it
also writes the matching ``GroupSchedule`` row.
"""
from apps.teachers.models import Group, GroupSchedule


def create_group_with_schedule(room=None, schedule_day=None, schedule_time=None,
                                duration_minutes=120, **group_kwargs):
    """
    Create a ``Group`` and, if a day/time is given, one ``GroupSchedule`` row
    for it carrying ``room``. Bypasses ``Group.full_clean()`` and the
    room-conflict check exactly like a bare ``Group.objects.create()`` did —
    tests that need the real validation call ``full_clean()``/``save()``
    themselves via ``GroupForm.save_with_schedules()``.
    """
    group = Group.objects.create(
        schedule_day=schedule_day,
        schedule_time=schedule_time,
        duration_minutes=duration_minutes,
        **group_kwargs,
    )
    if schedule_day and schedule_time:
        GroupSchedule.objects.create(
            group=group,
            day_of_week=schedule_day,
            start_time=schedule_time,
            duration=duration_minutes,
            room=room,
        )
    return group
