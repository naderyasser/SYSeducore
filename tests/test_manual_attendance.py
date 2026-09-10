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

    def test_backdated_lesson_joins_the_cycle_covering_its_date(self):
        # The exact shape of a migrated group: two legacy calendar-month
        # cycles (the second one closed *in the future*), plus the real open
        # cycle that started on the 3rd and overlaps the second.
        aug1 = date(2026, 8, 1)
        c1 = GroupCycle.objects.create(group=self.group, index=1, sessions_planned=8, is_legacy=True,
                                       started_on=aug1, closed_on=date(2026, 8, 31))
        c2 = GroupCycle.objects.create(group=self.group, index=2, sessions_planned=8, is_legacy=True,
                                       started_on=date(2026, 9, 1), closed_on=date(2026, 9, 30))
        c3 = GroupCycle.objects.create(group=self.group, index=3, sessions_planned=8,
                                       started_on=date(2026, 9, 3))
        existing = Session.objects.create(group=self.group, session_date=date(2026, 8, 24), cycle=c1, sequence_in_cycle=1)
        open_existing = Session.objects.create(group=self.group, session_date=date(2026, 9, 3), cycle=c3, sequence_in_cycle=1)

        def created(day):
            session, was_created, error = AttendanceService.ensure_manual_session(self.group, day)
            self.assertIsNone(error, error)
            self.assertTrue(was_created)
            return session

        # Inside the closed August cycle → joins it, numbered by date.
        s_aug20 = created(date(2026, 8, 20))
        self.assertEqual(s_aug20.cycle, c1)
        self.assertEqual(s_aug20.sequence_in_cycle, 1)
        existing.refresh_from_db()
        self.assertEqual(existing.sequence_in_cycle, 2)
        c1.refresh_from_db(); self.assertEqual(c1.started_on, aug1)  # untouched
        # Only the legacy September cycle covers the 2nd.
        self.assertEqual(created(date(2026, 9, 2)).cycle, c2)
        # Both cover the 5th — the open cycle wins.
        s_sep5 = created(date(2026, 9, 5))
        self.assertEqual(s_sep5.cycle, c3)
        self.assertEqual(s_sep5.sequence_in_cycle, 2)
        open_existing.refresh_from_db(); self.assertEqual(open_existing.sequence_in_cycle, 1)
        # Before the first cycle ever started → refused, nothing written.
        session, was_created, error = AttendanceService.ensure_manual_session(self.group, date(2026, 7, 15))
        self.assertIsNone(session); self.assertIn('أول دورة', error)
        self.assertFalse(Session.objects.filter(session_date=date(2026, 7, 15)).exists())
        # A marked lesson in a closed cycle never opens a Payment.
        self.assertTrue(self.record(on_date=date(2026, 8, 20))['success'])
        self.assertFalse(Payment.objects.exists())

    def test_gap_after_last_closed_cycle_joins_the_open_cycle(self):
        GroupCycle.objects.create(group=self.group, index=1, sessions_planned=4,
                                  started_on=self.today - timedelta(days=40), closed_on=self.today - timedelta(days=20))
        result = self.record(on_date=self.today - timedelta(days=10))
        self.assertTrue(result['success'], result)
        session = Session.objects.get(session_date=self.today - timedelta(days=10))
        self.assertIsNone(session.cycle.closed_on)
        self.assertEqual(session.cycle.index, 2)

    def test_group_without_any_cycle_yet_gets_one(self):
        result = self.record(on_date=self.today - timedelta(days=3))
        self.assertTrue(result['success'], result)
        self.assertEqual(GroupCycle.objects.filter(group=self.group).count(), 1)

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

    def test_session_only_before_first_cycle_is_400(self):
        GroupCycle.objects.create(group=self.group, index=1, sessions_planned=4,
                                  started_on=self.today - timedelta(days=30),
                                  closed_on=self.today - timedelta(days=10))
        self.client.force_login(self.supervisor)
        r = self.post_json({'group_id': self.group.pk, 'date': (self.today - timedelta(days=60)).isoformat()})
        self.assertEqual(r.status_code, 400)
        self.assertIn('أول دورة', r.json()['message'])
        # Inside the closed cycle is fine now.
        r = self.post_json({'group_id': self.group.pk, 'date': (self.today - timedelta(days=20)).isoformat()})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Session.objects.count(), 1)


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
        # Blank striped cells (lesson before the enrollment date) must be tappable.
        self.assertNotIn("state === 'not_enrolled'", html)
        self.assertNotIn(':not(.cell-not_enrolled)', html)

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


class SessionDeleteTests(ManualAttendanceBase):
    url = lambda self, pk: reverse('attendance:delete_session', args=[pk])

    def _old_session(self, days_back=10, **kw):
        # Older than SESSION_BACKFILL_DAYS so the recovery pass will not recreate it.
        return assign_to_cycle(Session.objects.create(
            group=self.group, session_date=self.today - timedelta(days=days_back), **kw))

    def test_delete_removes_rows_renumbers_and_recounts(self):
        s1 = self._old_session(14)
        s2 = self._old_session(7)
        self.record(on_date=s1.session_date)
        self.record(on_date=s2.session_date)
        payment = Payment.objects.get(student=self.student, group=self.group)
        self.assertEqual(payment.sessions_attended, 2)
        self.assertEqual(payment.entitlement_start_session, s1)

        self.client.force_login(self.supervisor)
        r = self.client.post(self.url(s1.pk))
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['removed_attendances'], 1)
        self.assertFalse(Session.objects.filter(pk=s1.pk).exists())
        self.assertFalse(Attendance.objects.filter(session_id=s1.pk).exists())
        s2.refresh_from_db()
        self.assertEqual(s2.sequence_in_cycle, 1)
        payment.refresh_from_db()
        self.assertEqual(payment.sessions_attended, 1)
        self.assertEqual(payment.entitlement_start_session, s2)
        log = ActivityLog.objects.get(action='session_delete')
        self.assertEqual(log.target_id, s1.pk)
        self.assertIn(data['redirect'], reverse('teachers:group_detail', args=[self.group.pk]))

    def test_recent_scheduled_lesson_must_be_cancelled_not_deleted(self):
        # Today is one of the group's scheduled weekdays (fixture) → inside the backfill window.
        session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        self.client.force_login(self.supervisor)
        r = self.client.post(self.url(session.pk))
        self.assertEqual(r.status_code, 409)
        self.assertIn('إلغاء الحصة', r.json()['message'])
        self.assertTrue(Session.objects.filter(pk=session.pk).exists())

    def test_recent_unscheduled_lesson_can_be_deleted(self):
        # Yesterday is not a scheduled weekday (fixture schedules today's weekday only).
        session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today - timedelta(days=1)))
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.post(self.url(session.pk)).status_code, 200)
        self.assertFalse(Session.objects.filter(pk=session.pk).exists())

    def test_delete_in_closed_cycle_renumbers_without_touching_payments(self):
        closed = GroupCycle.objects.create(group=self.group, index=1, sessions_planned=4,
                                           started_on=self.today - timedelta(days=40),
                                           closed_on=self.today - timedelta(days=20))
        a = Session.objects.create(group=self.group, session_date=self.today - timedelta(days=30), cycle=closed, sequence_in_cycle=1)
        b = Session.objects.create(group=self.group, session_date=self.today - timedelta(days=25), cycle=closed, sequence_in_cycle=2)
        Attendance.objects.create(student=self.student, session=a, status='present', supervisor=self.supervisor)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.post(self.url(a.pk)).status_code, 200)
        b.refresh_from_db()
        self.assertEqual(b.sequence_in_cycle, 1)
        self.assertFalse(Payment.objects.exists())

    def test_permissions_and_missing(self):
        session = self._old_session()
        self.assertEqual(self.client.post(self.url(session.pk)).status_code, 401)
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.post(self.url(session.pk)).status_code, 403)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(self.url(session.pk)).status_code, 405)
        self.assertEqual(self.client.post(self.url(999999)).status_code, 404)

    def test_session_page_shows_cancel_and_delete_to_desk_only(self):
        session = self._old_session()
        self.client.force_login(self.supervisor)
        html = self.client.get(reverse('attendance:session_detail', args=[session.pk])).content.decode()
        self.assertIn('id="cancel-session-btn"', html)
        self.assertIn('id="delete-session-btn"', html)
        self.client.force_login(self.teacher_user)
        html = self.client.get(reverse('attendance:session_detail', args=[session.pk])).content.decode()
        self.assertNotIn('delete-session-btn', html)
        self.assertNotIn('cancel-session-btn', html)


class ScannerClientRequestsTests(ManualAttendanceBase):
    def test_today_attendees_lists_exactly_what_the_counter_counts(self):
        session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        other = Student.objects.create(
            student_code='MAN009', full_name='طالبة متأخرة', gender='female',
            parent_phone='01098765409', student_phone='01011111109',
        )
        StudentGroupEnrollment.objects.create(student=other, group=self.group, is_active=True)
        Attendance.objects.create(student=self.student, session=session, status='present', supervisor=self.supervisor)
        Attendance.objects.create(student=other, session=session, status='late', supervisor=self.supervisor)
        absent = Student.objects.create(
            student_code='MAN010', full_name='غائب', gender='male',
            parent_phone='01098765410', student_phone='01011111110',
        )
        Attendance.objects.create(student=absent, session=session, status='absent', supervisor=self.supervisor)

        self.assertEqual(self.client.get(reverse('attendance:today_attendees')).status_code, 401)
        self.client.force_login(self.teacher_user)
        r = self.client.get(reverse('attendance:today_attendees'))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        stats = self.client.get(reverse('attendance:today_stats')).json()
        self.assertEqual(data['count'], stats['present'])
        self.assertEqual(data['count'], 2)
        names = {a['full_name'] for a in data['attendees']}
        self.assertEqual(names, {'طالب يدوي', 'طالبة متأخرة'})
        row = next(a for a in data['attendees'] if a['status'] == 'late')
        self.assertEqual(row['status_display'], 'متأخر')
        self.assertEqual(row['group_name'], self.group.group_name)
        self.assertEqual(row['session_id'], session.pk)

    def test_scanner_counter_opens_the_list_and_no_longer_threatens_a_10_minute_ban(self):
        self.client.force_login(self.supervisor)
        html = self.client.get(reverse('attendance:scanner')).content.decode()
        self.assertIn('onclick="showTodayAttendees()"', html)
        self.assertIn('id="attendeesModal"', html)
        self.assertNotIn('ممنوع الدخول', html)
        self.assertNotIn('قاعدة الـ 10 دقائق', html)
        self.assertIn('ولا يُمنع الدخول', html)


class SubscriptionPlanBadgeTests(ManualAttendanceBase):
    def setUp(self):
        super().setUp()
        self.student.subscription_plan = 'bundle_5'
        self.student.save(update_fields=['subscription_plan'])
        self.plain = Student.objects.create(
            student_code='MAN020', full_name='طالب عادي', gender='male',
            parent_phone='01098765420', student_phone='01011111120',
        )
        StudentGroupEnrollment.objects.create(student=self.plain, group=self.group, is_active=True)

    def test_default_is_regular_and_badge_text_empty(self):
        self.assertEqual(self.plain.subscription_plan, 'regular')
        self.assertFalse(self.plain.is_bundle)
        self.assertEqual(self.plain.plan_badge_label, '')
        self.assertEqual(self.student.plan_badge_label, 'باقة 5 مواد')

    def test_badge_on_every_screen_and_only_for_bundle_students(self):
        session = assign_to_cycle(Session.objects.create(group=self.group, session_date=self.today))
        Attendance.objects.create(student=self.student, session=session, status='present', supervisor=self.supervisor)
        Attendance.objects.create(student=self.plain, session=session, status='present', supervisor=self.supervisor)
        from apps.payments.models import Payment as P
        for st in (self.student, self.plain):
            P.objects.create(student=st, group=self.group, month=self.today.replace(day=1),
                             amount_due=Decimal('200'), amount_paid=0)
        self.client.force_login(self.supervisor)
        pages = [
            reverse('students:list'),
            reverse('students:detail', args=[self.student.pk]),
            reverse('payments:list'),
            reverse('teachers:group_detail', args=[self.group.pk]),
            reverse('attendance:session_detail', args=[session.pk]),
        ]
        for url in pages:
            html = self.client.get(url).content.decode()
            self.assertEqual(html.count('plan-badge-bundle'), html.count('باقة 5 مواد') and html.count('plan-badge-bundle'), url)
            self.assertIn('باقة 5 مواد', html, url)
        # The regular student's page carries no badge at all.
        html = self.client.get(reverse('students:detail', args=[self.plain.pk])).content.decode()
        self.assertNotIn('plan-badge-bundle', html)
        # Group page: exactly two badges (students table + grid header), not four.
        html = self.client.get(reverse('teachers:group_detail', args=[self.group.pk])).content.decode()
        self.assertEqual(html.count('plan-badge-bundle'), 2)

    def test_report_and_scanner_dossier_carry_the_plan(self):
        self.client.force_login(self.supervisor)
        html = self.client.get(reverse('students:report', args=[self.student.pk])).content.decode()
        self.assertIn('باقة 5 مواد', html)
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertEqual(dossier['plan'], 'bundle_5')
        self.assertEqual(dossier['plan_label'], 'باقة 5 مواد')
        self.assertEqual(AttendanceService.build_student_dossier(self.plain)['plan_label'], '')

    def test_form_saves_the_plan(self):
        self.client.force_login(self.supervisor)
        html = self.client.get(reverse('students:update', args=[self.student.pk])).content.decode()
        self.assertIn('id="id_subscription_plan"', html)
        self.assertIn('value="bundle_5" selected', html)
        r = self.client.post(reverse('students:update', args=[self.student.pk]), {
            'student_code': self.student.student_code, 'full_name': self.student.full_name,
            'gender': 'male', 'education_stage': '', 'education_year': '', 'education_type': 'general',
            'subscription_plan': 'regular', 'student_phone': '01011111111',
            'parent_phone': '01098765432', 'parent_name': '', 'date_of_birth': '',
            'school_name': '', 'address': '', 'is_active': 'on',
        })
        self.assertIn(r.status_code, (200, 302))
        self.student.refresh_from_db()
        self.assertEqual(self.student.subscription_plan, 'regular')
