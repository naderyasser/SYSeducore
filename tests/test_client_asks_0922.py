"""
Client asks of 2026-09-22 (the video walk-through): cancel one lesson,
rooms, reports drill-down, Excel export, student report.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import Session
from apps.attendance.services import AttendanceService
from tests.test_attendance import AttendanceTestMixin


@patch('apps.notifications.tasks.notify_session_cancelled', return_value=(0, 0))
class CancelOneLessonTests(AttendanceTestMixin, TestCase):
    """"عايز يقدر يلغي حصة واحدة بس مش المجموعة كلها"."""

    def setUp(self):
        super().setUp()
        self.client.login(username='sup_att', password='TestPass123!')
        self.next_week = timezone.localdate() + timedelta(days=7)   # same weekday

    def _cancel(self, day, reason='المدرس مسافر'):
        return self.client.post(
            reverse('attendance:cancel_upcoming_lesson', args=[self.group.pk]),
            {'date': day.isoformat(), 'reason': reason},
        )

    def test_a_future_lesson_is_cancelled_without_touching_the_schedule(self, _notify):
        r = self._cancel(self.next_week)
        self.assertEqual(r.status_code, 200, r.content)
        session = Session.objects.get(group=self.group, session_date=self.next_week)
        self.assertTrue(session.is_cancelled)
        self.assertIsNone(session.cycle_id, 'a cancelled lesson never counts in a cycle')
        self.assertEqual(session.cancellation_reason, 'المدرس مسافر')
        # The weekly schedule is untouched: the week after is still on.
        lessons = AttendanceService.upcoming_lessons(self.group, days=15)
        by_date = {l['date']: l for l in lessons}
        self.assertTrue(by_date[self.next_week]['cancelled'])
        self.assertFalse(by_date[self.next_week + timedelta(days=7)]['cancelled'])
        _notify.assert_called_once()

    def test_restore_brings_the_lesson_back(self, _notify):
        self._cancel(self.next_week)
        session = Session.objects.get(group=self.group, session_date=self.next_week)
        r = self.client.post(reverse('attendance:restore_upcoming_lesson', args=[session.pk]))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(Session.objects.filter(pk=session.pk).exists(),
                         'the placeholder row is removed; the day is a normal lesson again')

    def test_a_day_the_group_does_not_meet_is_refused(self, _notify):
        r = self._cancel(self.next_week + timedelta(days=1))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Session.objects.filter(group=self.group).exists())

    def test_a_past_date_is_refused(self, _notify):
        r = self._cancel(timezone.localdate() - timedelta(days=7))
        self.assertEqual(r.status_code, 400)

    def test_group_page_lists_upcoming_lessons_with_a_cancel_button(self, _notify):
        r = self.client.get(reverse('teachers:group_detail', args=[self.group.pk]))
        self.assertContains(r, 'الحصص القادمة')
        self.assertContains(r, self.next_week.isoformat())
        self.assertContains(r, 'إلغاء هذه الحصة')
