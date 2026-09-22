"""
Client asks of 2026-09-22 (the video walk-through): cancel one lesson,
rooms, reports drill-down, Excel export, student report.
"""
from datetime import timedelta
from decimal import Decimal
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


class RoomSlotTests(AttendanceTestMixin, TestCase):
    """"يحذف مدرس من قاعة في وقت معين، مش يحذف المجموعة كلها" + تعديل القاعة."""

    def setUp(self):
        super().setUp()
        self.client.login(username='sup_att', password='TestPass123!')
        from apps.teachers.models import GroupSchedule, Room
        self.slot = GroupSchedule.objects.get(group=self.group)
        self.other_room = Room.objects.create(name='قاعة 2', capacity=20)

    def _post(self, **data):
        return self.client.post(
            reverse('teachers:room_slot_update', args=[self.slot.pk]), data)

    def test_unassign_frees_the_room_and_keeps_the_lesson(self):
        r = self._post(action='unassign')
        self.assertEqual(r.status_code, 200, r.content)
        self.slot.refresh_from_db()
        self.assertIsNone(self.slot.room_id)
        self.group.refresh_from_db()
        self.assertTrue(self.group.is_active)
        self.assertEqual(self.group.schedules.count(), 1)

    def test_move_to_another_room_and_time(self):
        r = self._post(action='update', day=self.slot.day_of_week, start_time='17:30',
                       duration='90', room_id=str(self.other_room.pk))
        self.assertEqual(r.status_code, 200, r.content)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.room_id, self.other_room.pk)
        self.assertEqual(self.slot.start_time.strftime('%H:%M'), '17:30')
        self.group.refresh_from_db()
        self.assertEqual(self.group.schedule_time.strftime('%H:%M'), '17:30')

    def test_an_overlapping_move_is_refused(self):
        from datetime import time as _t
        from tests.factories import create_group_with_schedule
        create_group_with_schedule(
            group_name='مجموعة أخرى', teacher=self.teacher, room=self.other_room,
            schedule_day=self.slot.day_of_week, schedule_time=_t(17, 0),
            duration_minutes=120, standard_fee=Decimal('100.00'),
        )
        r = self._post(action='update', day=self.slot.day_of_week, start_time='17:30',
                       duration='90', room_id=str(self.other_room.pk))
        self.assertEqual(r.status_code, 400)
        self.assertIn('تعارض', r.json()['message'])

    def test_the_only_slot_of_a_group_cannot_be_deleted(self):
        r = self._post(action='delete')
        self.assertEqual(r.status_code, 400)

    def test_room_edit_page_lists_its_slots(self):
        r = self.client.get(reverse('teachers:room_update', args=[self.room.pk]))
        self.assertContains(r, 'مواعيد القاعة')
        self.assertContains(r, self.group.group_name)
        self.assertContains(r, 'إخلاء القاعة')

    def test_book_the_room_for_a_group_on_a_new_day(self):
        day = 'Friday' if self.slot.day_of_week != 'Friday' else 'Monday'
        r = self.client.post(reverse('teachers:room_slot_create', args=[self.other_room.pk]),
                             {'group_id': self.group.pk, 'day': day,
                              'start_time': '10:00', 'duration': '60'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.group.schedules.count(), 2)


class ReportDrillDownTests(AttendanceTestMixin, TestCase):
    """"كل رقم في التقرير عايزه clickable" — التصفية الشهرية والتقرير الشامل."""

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model
        from apps.payments.models import Payment
        from apps.students.models import Student, StudentGroupEnrollment
        get_user_model().objects.create_user(username='boss', password='pw12345!', role='admin')
        self.client.login(username='boss', password='pw12345!')
        self.month = timezone.localdate().replace(day=1)
        self.other = Student.objects.create(student_code='ATT002', full_name='طالب مديون',
                                            parent_phone='01099999999')
        StudentGroupEnrollment.objects.create(student=self.other, group=self.group, is_active=True)
        Payment.objects.create(student=self.student, group=self.group, month=self.month,
                               amount_due=Decimal('200'), amount_paid=Decimal('200'), status='paid')
        Payment.objects.create(student=self.other, group=self.group, month=self.month,
                               amount_due=Decimal('200'), amount_paid=Decimal('0'), status='unpaid')

    def _tsfya(self, **params):
        return self.client.get(reverse('reports:tsfya'), {'month': self.month.strftime('%Y-%m'), **params})

    def test_every_tile_links_to_its_rows(self):
        body = self._tsfya().content.decode()
        for status in ('paid', 'partial', 'unpaid', 'collected', 'owing', 'split'):
            self.assertIn(f'status={status}#records', body, status)

    def test_unpaid_drill_lists_only_the_unpaid(self):
        r = self._tsfya(status='unpaid')
        records = [p.student.full_name for p in r.context['page_obj']]
        self.assertEqual(records, ['طالب مديون'])
        self.assertContains(r, 'إلغاء التصفية')

    def test_collection_rate_opens_who_paid_and_who_did_not(self):
        r = self._tsfya(status='split', group=str(self.group.pk))
        self.assertEqual([p.student.full_name for p in r.context['split_paid']], ['طالب حضور'])
        self.assertEqual([p.student.full_name for p in r.context['split_unpaid']], ['طالب مديون'])

    def test_comprehensive_detail_absent_and_members(self):
        self._attend(day_offset=0, status='absent')
        url = reverse('reports:comprehensive')
        r = self.client.get(url, {'detail': 'absent'})
        self.assertEqual([a.student.full_name for a in r.context['detail_page']], ['طالب حضور'])
        r = self.client.get(url, {'detail': 'members', 'group': self.group.pk})
        self.assertEqual(r.context['detail_page'].paginator.count, 2)
        r = self.client.get(url, {'detail': 'unpaid'})
        self.assertEqual([p.student.full_name for p in r.context['detail_page']], ['طالب مديون'])
