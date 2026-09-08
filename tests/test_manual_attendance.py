"""
Manual attendance — the desk marking a student by hand, today or backdated.

Covers ``AttendanceService.record_manual``, the ``attendance:manual_attendance``
endpoint, and the three screens that call it (group grid, session roster,
student page).
"""
import json
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import Session, Attendance, ActivityLog, ExceptionRecord
from apps.attendance.services import AttendanceService
from apps.payments.models import Payment
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.cycles import assign_to_cycle
from apps.teachers.models import Teacher, Room, GroupCycle
from tests.factories import create_group_with_schedule

User = get_user_model()


class ManualAttendanceBase(TestCase):
    def setUp(self):
        self.supervisor = User.objects.create_user(username='desk', password='pw12345!', role='supervisor')
        self.teacher_user = User.objects.create_user(username='tch', password='pw12345!', role='teacher')
        self.room = Room.objects.create(name='قاعة يدوي', capacity=30)
        self.teacher = Teacher.objects.create(
            full_name='مدرس يدوي', phone='01012345678',
            specialization='فيزياء', hire_date=date(2024, 1, 1),
        )
        self.today = timezone.localdate()
        # Scheduled on today's weekday so "today" is a scheduled day and
        # "yesterday" is not — both cases are exercised below.
        self.group = create_group_with_schedule(
            group_name='مجموعة يدوي', teacher=self.teacher, room=self.room,
            schedule_day=self.today.strftime('%A'), schedule_time=time(16, 0),
            duration_minutes=120, standard_fee=Decimal('200.00'),
            center_percentage=Decimal('30.00'), sessions_per_month=4,
        )
        self.student = Student.objects.create(
            student_code='MAN001', full_name='طالب يدوي', gender='male',
            parent_phone='01098765432', student_phone='01011111111',
        )
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group, financial_status='normal', is_active=True,
        )

    def record(self, on_date=None, status='present', student=None, group=None):
        return AttendanceService.record_manual(
            student=student or self.student, group=group or self.group,
            on_date=on_date or self.today, status=status, supervisor=self.supervisor,
        )


class RecordManualServiceTests(ManualAttendanceBase):
    def test_today_creates_session_and_attendance(self):
        result = self.record()
        self.assertTrue(result['success'], result)
        self.assertTrue(result['created'])
        session = Session.objects.get(group=self.group, session_date=self.today)
        self.assertIsNotNone(session.cycle_id)
        self.assertEqual(session.sequence_in_cycle, 1)
        att = Attendance.objects.get(student=self.student, session=session)
        self.assertEqual(att.status, 'present')
        self.assertEqual(att.supervisor, self.supervisor)
        self.assertIsNone(result['warning'])

    def test_backdated_mark_dates_the_row_on_the_lesson_not_today(self):
        past = self.today - timedelta(days=7)  # same weekday → scheduled at 16:00
        result = self.record(on_date=past)
        self.assertTrue(result['success'], result)
        att = Attendance.objects.get(student=self.student, session__session_date=past)
        local = timezone.localtime(att.scan_time)
        self.assertEqual(local.date(), past)
        self.assertEqual(local.time(), time(16, 0))

    def test_backdated_session_is_numbered_in_date_order(self):
        self.record()  # today → seq 1
        past = self.today - timedelta(days=7)
        self.record(on_date=past)
        seqs = dict(Session.objects.filter(group=self.group).values_list('session_date', 'sequence_in_cycle'))
        self.assertEqual(seqs[past], 1)
        self.assertEqual(seqs[self.today], 2)

    def test_unscheduled_day_is_allowed_with_a_warning(self):
        result = self.record(on_date=self.today - timedelta(days=1))
        self.assertTrue(result['success'], result)
        self.assertIn('تعويضية', result['warning'])
        att = Attendance.objects.get(student=self.student)
        self.assertEqual(timezone.localtime(att.scan_time).hour, 12)

    def test_future_date_refused(self):
        result = self.record(on_date=self.today + timedelta(days=1))
        self.assertFalse(result['success'])
        self.assertFalse(Session.objects.exists())

    def test_not_enrolled_refused(self):
        other = Student.objects.create(
            student_code='MAN002', full_name='غريب', gender='male',
            parent_phone='01098765400', student_phone='01011111100',
        )
        result = self.record(student=other)
        self.assertFalse(result['success'])
        self.assertIn('غير مسجل', result['message'])

    def test_invalid_status_refused(self):
        self.assertFalse(self.record(status='exception')['success'])
        self.assertFalse(self.record(status='banana')['success'])

    def test_cancelled_session_refused(self):
        Session.objects.create(group=self.group, session_date=self.today, is_cancelled=True,
                               cancellation_reason='إجازة')
        result = self.record()
        self.assertFalse(result['success'])
        self.assertIn('ملغاة', result['message'])

    def test_new_session_inside_or_before_closed_cycle_refused(self):
        start = self.today - timedelta(days=30)
        GroupCycle.objects.create(group=self.group, index=1, sessions_planned=4,
                                  started_on=start, closed_on=self.today - timedelta(days=10))
        for days_back in (20, 45):  # inside the closed cycle, and before it ever started
            result = self.record(on_date=self.today - timedelta(days=days_back))
            self.assertFalse(result['success'])
            self.assertIn('مغلقة', result['message'])
        self.assertFalse(Session.objects.exists())
        # After the close is the open cycle — allowed.
        self.assertTrue(self.record(on_date=self.today - timedelta(days=5))['success'])

    def test_existing_session_in_closed_cycle_marks_without_opening_a_payment(self):
        start = self.today - timedelta(days=30)
        closed = GroupCycle.objects.create(group=self.group, index=1, sessions_planned=4,
                                           started_on=start, closed_on=self.today - timedelta(days=10))
        past = self.today - timedelta(days=20)
        Session.objects.create(group=self.group, session_date=past, cycle=closed, sequence_in_cycle=2)
        result = self.record(on_date=past)
        self.assertTrue(result['success'], result)
        self.assertTrue(Attendance.objects.filter(student=self.student, session__session_date=past).exists())
        self.assertFalse(Payment.objects.exists())

    def test_exception_row_is_never_overwritten(self):
        session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        exc = ExceptionRecord.objects.create(
            student=self.student, group=self.group, exception_type='payment',
            reason_type='other', approved_by=self.supervisor,
        )
        Attendance.objects.create(student=self.student, session=session, status='exception',
                                  exception_record=exc, supervisor=self.supervisor)
        result = self.record(status='absent')
        self.assertFalse(result['success'])
        att = Attendance.objects.get(student=self.student, session=session)
        self.assertEqual(att.status, 'exception')
        self.assertEqual(att.exception_record, exc)

    def test_status_change_and_clear_recount_payment_sessions(self):
        self.record()
        payment = Payment.objects.get(student=self.student, group=self.group)
        self.assertEqual(payment.sessions_attended, 1)

        result = self.record(status='late')
        self.assertTrue(result['success'])
        self.assertFalse(result['created'])
        self.assertEqual(Attendance.objects.get(student=self.student).status, 'late')
        payment.refresh_from_db()
        self.assertEqual(payment.sessions_attended, 1)

        result = self.record(status='clear')
        self.assertTrue(result['success'])
        self.assertIsNone(result['attendance'])
        self.assertFalse(Attendance.objects.filter(student=self.student).exists())
        payment.refresh_from_db()
        self.assertEqual(payment.sessions_attended, 0)

    def test_clear_with_no_session_is_a_noop(self):
        result = self.record(status='clear', on_date=self.today - timedelta(days=3))
        self.assertTrue(result['success'])
        self.assertFalse(Session.objects.exists())

    def test_group_without_cycle_billing_leaves_payments_alone(self):
        self.group.sessions_per_month = 0
        self.group.save(update_fields=['sessions_per_month'])
        result = self.record()
        self.assertTrue(result['success'], result)
        self.assertFalse(Payment.objects.exists())


class ManualAttendanceEndpointTests(ManualAttendanceBase):
    url = reverse('attendance:manual_attendance')

    def post_json(self, payload, **kw):
        return self.client.post(self.url, data=json.dumps(payload), content_type='application/json', **kw)

    def test_anonymous_is_401(self):
        r = self.post_json({'group_id': self.group.pk, 'student_id': self.student.pk})
        self.assertEqual(r.status_code, 401)

    def test_teacher_is_403(self):
        self.client.force_login(self.teacher_user)
        r = self.post_json({'group_id': self.group.pk, 'student_id': self.student.pk})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Attendance.objects.exists())

    def test_get_not_allowed(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_supervisor_marks_backdated_and_logs(self):
        self.client.force_login(self.supervisor)
        past = (self.today - timedelta(days=7)).isoformat()
        r = self.post_json({'group_id': self.group.pk, 'student_id': self.student.pk,
                            'date': past, 'status': 'late'})
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['attendance']['status'], 'late')
        self.assertTrue(Attendance.objects.filter(session__session_date=past, status='late').exists())
        log = ActivityLog.objects.get(action='attendance_manual')
        self.assertEqual(log.user, self.supervisor)
        self.assertEqual(log.target_model, 'Attendance')

    def test_form_encoded_body_also_works(self):
        self.client.force_login(self.supervisor)
        r = self.client.post(self.url, {'group_id': self.group.pk, 'student_id': self.student.pk,
                                        'status': 'absent'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Attendance.objects.get().status, 'absent')

    def test_empty_body_is_400_not_500(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.post(self.url).status_code, 400)
        r = self.client.post(self.url, data='{not json', content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_bad_date_and_unknown_student_are_400(self):
        self.client.force_login(self.supervisor)
        r = self.post_json({'group_id': self.group.pk, 'student_id': self.student.pk, 'date': '2026-13-45'})
        self.assertEqual(r.status_code, 400)
        r = self.post_json({'group_id': self.group.pk, 'student_id': 999999})
        self.assertEqual(r.status_code, 400)

    def test_refusal_from_service_is_400_with_message(self):
        self.client.force_login(self.supervisor)
        r = self.post_json({'group_id': self.group.pk, 'student_id': self.student.pk,
                            'date': (self.today + timedelta(days=1)).isoformat()})
        self.assertEqual(r.status_code, 400)
        self.assertIn('مستقبلي', r.json()['message'])

    def test_session_only_creates_the_lesson(self):
        self.client.force_login(self.supervisor)
        past = (self.today - timedelta(days=2)).isoformat()
        r = self.post_json({'group_id': self.group.pk, 'date': past})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['created'])
        session = Session.objects.get(group=self.group, session_date=past)
        self.assertEqual(session.sequence_in_cycle, 1)
        self.assertFalse(Attendance.objects.exists())
        # Idempotent
        r = self.post_json({'group_id': self.group.pk, 'date': past})
        self.assertFalse(r.json()['created'])
        self.assertEqual(Session.objects.count(), 1)
        # Never in the future
        r = self.post_json({'group_id': self.group.pk, 'date': (self.today + timedelta(days=1)).isoformat()})
        self.assertEqual(r.status_code, 400)

    def test_session_only_refuses_a_date_in_a_closed_cycle(self):
        GroupCycle.objects.create(group=self.group, index=1, sessions_planned=4,
                                  started_on=self.today - timedelta(days=30),
                                  closed_on=self.today - timedelta(days=10))
        self.client.force_login(self.supervisor)
        r = self.post_json({'group_id': self.group.pk, 'date': (self.today - timedelta(days=20)).isoformat()})
        self.assertEqual(r.status_code, 400)
        self.assertIn('مغلقة', r.json()['message'])
        self.assertEqual(Session.objects.count(), 0)


class ManualAttendanceScreensTests(ManualAttendanceBase):
    def test_session_page_lists_every_enrolled_student_with_mark_buttons_for_desk(self):
        session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        other = Student.objects.create(
            student_code='MAN003', full_name='طالب بلا سجل', gender='female',
            parent_phone='01098765401', student_phone='01011111101',
        )
        StudentGroupEnrollment.objects.create(student=other, group=self.group, is_active=True)
        Attendance.objects.create(student=self.student, session=session, status='present',
                                  supervisor=self.supervisor)

        self.client.force_login(self.supervisor)
        r = self.client.get(reverse('attendance:session_detail', args=[session.pk]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('طالب بلا سجل', html)
        self.assertIn('data-mark="present"', html)
        self.assertIn('data-manual-attendance-url', html)
        self.assertEqual(html.count('<tr data-student-id='), 2)

    def test_session_page_shows_no_buttons_for_a_student_removed_from_the_group(self):
        session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        Attendance.objects.create(student=self.student, session=session, status='present',
                                  supervisor=self.supervisor)
        self.enrollment.is_active = False
        self.enrollment.save(update_fields=['is_active'])
        self.client.force_login(self.supervisor)
        html = self.client.get(reverse('attendance:session_detail', args=[session.pk])).content.decode()
        self.assertIn('أُزيل من المجموعة', html)
        self.assertNotIn('data-mark="present"', html)

    def test_session_page_hides_controls_from_teachers(self):
        session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        self.client.force_login(self.teacher_user)
        r = self.client.get(reverse('attendance:session_detail', args=[session.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('data-mark=', r.content.decode())

    def test_group_grid_cells_carry_date_and_add_lesson_form_for_desk(self):
        assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        self.client.force_login(self.supervisor)
        r = self.client.get(reverse('teachers:group_detail', args=[self.group.pk]))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn(f'data-date="{self.today.isoformat()}"', html)
        self.assertIn(f'<tr data-student-id="{self.student.pk}">', html)
        self.assertIn('id="add-session-form"', html)
        self.assertIn('ManualAttendance.mark', html)

    def test_group_page_is_desk_only(self):
        # The group page itself is supervisor-gated, so the grid controls
        # never reach a teacher — the endpoint is gated independently anyway.
        assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        self.client.force_login(self.teacher_user)
        r = self.client.get(reverse('teachers:group_detail', args=[self.group.pk]))
        self.assertEqual(r.status_code, 403)

    def test_student_page_offers_manual_modal_to_desk_only(self):
        url = reverse('students:detail', args=[self.student.pk])
        self.client.force_login(self.supervisor)
        html = self.client.get(url).content.decode()
        self.assertIn('id="manualAttendanceModal"', html)
        self.assertIn(f'value="{self.group.pk}"', html)
        self.assertIn(f'max="{self.today.isoformat()}"', html)

        self.client.force_login(self.teacher_user)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('manualAttendanceModal', r.content.decode())
