"""
Client, 2026-10-27: «امكانيه تكرار نفس التاريخ بحيث بدل الحصه تتحسب حصتين بساعتين
واضافه حصص اضافيه». A double lesson is two Session rows on one date (slot 1 and
its twin, slot 2) that always carry the same attendance; an extra lesson added
for today on a day off the timetable can be scanned into.
"""
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import Attendance, Session
from apps.attendance.services import AttendanceService
from apps.notifications.models import WhatsAppMessage
from apps.payments.models import Payment
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.cycles import assign_to_cycle
from apps.teachers.models import Room, Teacher
from tests.factories import create_group_with_schedule

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


class DoubleLessonTest(TestCase):

    def setUp(self):
        self.sup = get_user_model().objects.create_user(username='sup27', password='pw12345!', role='supervisor')
        self.teacher = Teacher.objects.create(full_name='مدرس مزدوج', phone='01000000027', email='d@t.com',
                                              specialization='Math', hire_date=timezone.localdate())
        self.today = timezone.localdate()
        now_local = timezone.localtime()
        if now_local.time() < time(0, 20):
            self.skipTest('needs a lesson that started 15 minutes ago today')
        start = (now_local - timedelta(minutes=15)).time().replace(second=0, microsecond=0)
        self.group = create_group_with_schedule(
            group_name='مجموعة مزدوجة', teacher=self.teacher,
            room=Room.objects.create(name='قاعة مزدوجة', capacity=20),
            schedule_day=DAYS[self.today.weekday()], schedule_time=start,
            duration_minutes=120, standard_fee=200, sessions_per_month=8,
        )
        self.student = Student.objects.create(student_code='D27', full_name='طالب مزدوج', parent_phone='01000000028')
        enr = StudentGroupEnrollment.objects.create(student=self.student, group=self.group)
        StudentGroupEnrollment.objects.filter(pk=enr.pk).update(enrolled_at=timezone.now() - timedelta(days=30))
        self.session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        Payment.objects.create(student=self.student, group=self.group, cycle=self.session.cycle,
                               month=self.today.replace(day=1), amount_due=200, amount_paid=200,
                               status='paid', paid_on=self.today - timedelta(days=1))

    def _payment(self):
        return Payment.objects.get(student=self.student, group=self.group)

    def test_make_double_counts_two_and_scan_marks_both(self):
        twin, error = AttendanceService.make_double(self.session)
        self.assertIsNone(error)
        self.assertEqual((twin.slot, twin.cycle_id), (2, self.session.cycle_id))
        result = AttendanceService.process_scan(self.student.student_code, self.sup)
        self.assertTrue(result['success'], result.get('message'))
        statuses = list(Attendance.objects.filter(student=self.student).order_by('session__slot')
                        .values_list('status', flat=True))
        self.assertEqual(len(statuses), 2)
        self.assertEqual(statuses[0], statuses[1])
        self.assertEqual(self._payment().sessions_attended, 2)

    def test_manual_edit_and_clear_follow_to_the_twin(self):
        AttendanceService.make_double(self.session)
        AttendanceService.record_manual(self.student, self.group, self.today, 'absent', self.sup)
        self.assertEqual(list(Attendance.objects.filter(student=self.student).values_list('status', flat=True)),
                         ['absent', 'absent'])
        AttendanceService.record_manual(self.student, self.group, self.today, 'clear', self.sup)
        self.assertFalse(Attendance.objects.filter(student=self.student).exists())

    def test_existing_rows_are_copied_when_made_double(self):
        AttendanceService.record_manual(self.student, self.group, self.today, 'present', self.sup)
        AttendanceService.make_double(self.session)
        self.assertEqual(Attendance.objects.filter(student=self.student, status='present').count(), 2)
        self.assertEqual(self._payment().sessions_attended, 2)

    def test_cancel_and_restore_take_the_twin_along(self):
        twin, _ = AttendanceService.make_double(self.session)
        self.session.is_cancelled = True
        self.session.save()
        AttendanceService.follow_cancellation(self.session)
        twin.refresh_from_db()
        self.assertTrue(twin.is_cancelled)
        self.assertIsNone(twin.sequence_in_cycle)

    def test_undo_double(self):
        AttendanceService.make_double(self.session)
        AttendanceService.record_manual(self.student, self.group, self.today, 'present', self.sup)
        ok, _ = AttendanceService.undo_double(self.session)
        self.assertTrue(ok)
        self.assertEqual(Session.objects.filter(group=self.group, session_date=self.today).count(), 1)
        self.assertEqual(self._payment().sessions_attended, 1)

    def test_one_message_for_a_double_lesson(self):
        from unittest.mock import patch
        from apps.notifications.tasks import send_attendance_notifications_task
        AttendanceService.make_double(self.session)
        AttendanceService.record_manual(self.student, self.group, self.today, 'present', self.sup)
        with self.settings(NOTIFICATION_METHOD='whatsapp', WAPILOT_API_TOKEN='t', WAPILOT_INSTANCE_ID='i'), \
                patch('apps.notifications.services.NotificationService.send_text', return_value={'success': True}):
            send_attendance_notifications_task()
        self.assertEqual(WhatsAppMessage.objects.filter(student=self.student).count(), 1)

    def test_toggle_endpoint_and_add_session_checkbox(self):
        self.client.login(username='sup27', password='pw12345!')
        url = reverse('attendance:toggle_double_session', args=[self.session.pk])
        r = self.client.post(url, {'action': 'make'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(r.json()['success'], r.json())
        r = self.client.post(url, {'action': 'undo'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTrue(r.json()['success'], r.json())
        page = self.client.get(reverse('attendance:session_detail', args=[self.session.pk]))
        self.assertContains(page, 'تتحسب حصتين')


class ExtraLessonScanTest(TestCase):
    """An extra lesson added for today on a day off the timetable is scannable."""

    def test_scan_into_extra_lesson(self):
        sup = get_user_model().objects.create_user(username='sup27b', password='pw12345!', role='supervisor')
        teacher = Teacher.objects.create(full_name='مدرس إضافي', phone='01000000029', email='e@t.com',
                                         specialization='Math', hire_date=timezone.localdate())
        today = timezone.localdate()
        other_day = DAYS[(today.weekday() + 3) % 7]
        group = create_group_with_schedule(
            group_name='مجموعة إضافية', teacher=teacher, room=Room.objects.create(name='قاعة إضافية', capacity=20),
            schedule_day=other_day, schedule_time=time(10, 0), standard_fee=200, sessions_per_month=8,
        )
        student = Student.objects.create(student_code='E27', full_name='طالب إضافي', parent_phone='01000000030')
        StudentGroupEnrollment.objects.create(student=student, group=group)
        refused = AttendanceService.process_scan(student.student_code, sup)
        self.assertFalse(refused['success'])
        session, _, error = AttendanceService.ensure_manual_session(group, today)
        self.assertIsNone(error)
        Payment.objects.create(student=student, group=group, cycle=session.cycle, month=today.replace(day=1),
                               amount_due=200, amount_paid=200, status='paid', paid_on=today)
        result = AttendanceService.process_scan(student.student_code, sup)
        self.assertTrue(result['success'], result.get('message'))
        self.assertEqual(Attendance.objects.get(student=student, session=session).status, 'present')
