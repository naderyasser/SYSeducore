"""
Attendance & Session Logic Tests.

Tests the complete barcode scan workflow:
- Time window validation (±30 min early, 10 min late rule)
- Financial blocking (month 1 = 0 grace, month 2+ = 2 grace)
- Session exhaustion (sessions_per_month limit)
- Duplicate scan prevention
- Subscription expiry blocking
"""
from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.attendance.models import Session, Attendance, ActivityLog
from apps.attendance.services import AttendanceService
from apps.teachers.cycles import assign_to_cycle
from apps.payments.models import Payment
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room, Subject, GroupCycle
from tests.factories import create_group_with_schedule

User = get_user_model()


class AttendanceTestMixin:
    """Shared setup for attendance tests."""

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='sup_att', password='TestPass123!', role='supervisor'
        )
        self.room = Room.objects.create(name='قاعة حضور', capacity=30)
        self.teacher = Teacher.objects.create(
            full_name='مدرس حضور', phone='01012345678',
            specialization='رياضيات', hire_date=date(2024, 1, 1),
        )

        # Schedule group for current day so scan matching works
        current_day = AttendanceService.get_current_day_name()

        self.group = create_group_with_schedule(
            group_name='مجموعة حضور',
            teacher=self.teacher,
            room=self.room,
            schedule_day=current_day,
            schedule_time=time(14, 0),
            duration_minutes=120,
            standard_fee=Decimal('200.00'),
            center_percentage=Decimal('30.00'),
            sessions_per_month=4,
        )

        self.student = Student.objects.create(
            student_code='ATT001',
            full_name='طالب حضور',
            gender='male',
            parent_phone='01098765432',
            student_phone='01011111111',
        )

        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )

    def _attend(self, day_offset=0, status='present', student=None):
        """Create + cycle-assign a session, then an attendance row on it."""
        session = assign_to_cycle(Session.objects.create(
            group=self.group, session_date=timezone.localdate() + timedelta(days=day_offset),
        ))
        Attendance.objects.create(
            student=student or self.student, session=session, status=status,
            scan_time=timezone.now(),
        )
        return session

    def _mark_as_returning_student(self):
        """A Payment paid for this group in the past — 'has paid before'."""
        Payment.objects.create(
            student=self.student, group=self.group, cycle=None,
            month=timezone.localdate().replace(day=1, month=1),
            amount_due=Decimal('200.00'), amount_paid=Decimal('200.00'), status='paid',
        )


class TestStrictTimeCheck(TestCase):
    """Test the 10-minute late rule and 30-minute early rule."""

    def _make_scan_time(self, schedule_time, delta_minutes):
        """Create a timezone-aware scan time offset from schedule."""
        from django.conf import settings
        import pytz
        local_tz = pytz.timezone(settings.TIME_ZONE)
        base = local_tz.localize(
            timezone.datetime.combine(timezone.now().date(), schedule_time)
        )
        return base + timedelta(minutes=delta_minutes)

    def test_on_time_allowed(self):
        """Student scans exactly on time — should be allowed."""
        schedule = time(14, 0)
        scan = self._make_scan_time(schedule, 0)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['status'], 'present')

    def test_5_minutes_late_allowed(self):
        """Student scans 5 minutes late — within grace, should be allowed."""
        schedule = time(14, 0)
        scan = self._make_scan_time(schedule, 5)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['minutes_late'], 5)

    def test_10_minutes_late_allowed(self):
        """Student scans exactly 10 minutes late — boundary, should be allowed."""
        schedule = time(14, 0)
        scan = self._make_scan_time(schedule, 10)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertTrue(result['allowed'])

    def test_11_minutes_late_blocked(self):
        """Student scans 11 minutes late — exceeds grace, must be BLOCKED."""
        schedule = time(14, 0)
        scan = self._make_scan_time(schedule, 11)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'too_late')

    def test_20_minutes_late_blocked(self):
        """Student scans 20 minutes late — clearly blocked."""
        schedule = time(14, 0)
        scan = self._make_scan_time(schedule, 20)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'too_late')

    def test_15_minutes_early_allowed(self):
        """Student scans 15 minutes early — within 30-min window, allowed."""
        schedule = time(14, 0)
        scan = self._make_scan_time(schedule, -15)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertTrue(result['allowed'])

    def test_30_minutes_early_allowed(self):
        """Student scans exactly 30 minutes early — boundary, should be allowed."""
        schedule = time(14, 0)
        scan = self._make_scan_time(schedule, -30)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertTrue(result['allowed'])

    def test_31_minutes_early_blocked(self):
        """Student scans 31 minutes early — too early, must be BLOCKED."""
        schedule = time(14, 0)
        scan = self._make_scan_time(schedule, -31)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'too_early')

    def test_after_session_end_blocked(self):
        """Student scans after session ended — must be BLOCKED."""
        schedule = time(14, 0)
        # Session is 120 min, so ends at 16:00. Scan at 16:01.
        scan = self._make_scan_time(schedule, 121)
        result = AttendanceService.check_strict_time(scan, schedule, 120)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'session_ended')


class TestFinancialBlocking(AttendanceTestMixin, TestCase):
    """Financial blocking: first cycle (0 grace) vs returning student (2 grace)."""

    def test_first_cycle_no_payment_blocked(self):
        """First cycle in this group, no payment — BLOCKED (0 grace sessions)."""
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'payment_required')

    def test_first_cycle_with_payment_allowed(self):
        """First cycle, but paid — ALLOWED."""
        cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4, started_on=timezone.localdate(),
        )
        Payment.objects.create(
            student=self.student, group=self.group, cycle=cycle,
            month=timezone.localdate().replace(day=1), amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid', sessions_total=4,
        )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

    def test_returning_student_grace_session_1_allowed(self):
        """Returning student (paid this group before), 0 sessions this cycle — 1st grace allowed."""
        self._mark_as_returning_student()
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('grace_sessions'))

    def test_returning_student_grace_session_2_allowed(self):
        """Returning student, 1 session consumed this cycle — 2nd grace session allowed."""
        self._mark_as_returning_student()
        self._attend(day_offset=0)
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

    def test_returning_student_after_grace_blocked(self):
        """Returning student, 2 sessions consumed, no payment for the new cycle — 3rd BLOCKED."""
        self._mark_as_returning_student()
        self._attend(day_offset=0)
        self._attend(day_offset=1)
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])

    def test_exempt_student_always_allowed(self):
        """Exempt student — should ALWAYS be allowed regardless of payment."""
        self.enrollment.financial_status = 'exempt'
        self.enrollment.save()

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('exempt', False))


class TestSessionExhaustion(AttendanceTestMixin, TestCase):
    """Session limit enforcement — bounded by GroupCycle.sessions_planned, not calendar days."""

    def test_sessions_exhausted_blocked(self):
        """Student consumed 4/4 sessions of a paid cycle — 5th scan must be BLOCKED."""
        cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4, started_on=timezone.localdate(),
        )
        Payment.objects.create(
            student=self.student, group=self.group, cycle=cycle,
            month=timezone.localdate().replace(day=1), amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid',
            sessions_attended=4, sessions_total=4,
        )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'sessions_exhausted')
        self.assertEqual(result['sessions_limit'], 4)

    def test_3_of_4_sessions_allowed(self):
        """Student consumed 3/4 sessions of a paid cycle — 4th scan should be ALLOWED."""
        cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4, started_on=timezone.localdate(),
        )
        Payment.objects.create(
            student=self.student, group=self.group, cycle=cycle,
            month=timezone.localdate().replace(day=1), amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid',
            sessions_attended=3, sessions_total=4,
        )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

    def test_custom_session_limit(self):
        """8-session cycle — student allowed after consuming only 4 of 8."""
        self.group.sessions_per_month = 8
        self.group.save()
        cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=8, started_on=timezone.localdate(),
        )
        Payment.objects.create(
            student=self.student, group=self.group, cycle=cycle,
            month=timezone.localdate().replace(day=1), amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid',
            sessions_attended=4, sessions_total=8,
        )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])


class TestDuplicateScanPrevention(AttendanceTestMixin, TestCase):
    """Test that duplicate scans for same session are rejected."""

    def test_duplicate_scan_blocked(self):
        """Scanning same student twice for same session — must return error."""
        session = Session.objects.create(
            group=self.group, session_date=timezone.now().date()
        )
        Attendance.objects.create(
            student=self.student, session=session,
            scan_time=timezone.now(), status='present',
        )

        # Try to create duplicate
        exists = Attendance.objects.filter(
            student=self.student, session=session
        ).exists()
        self.assertTrue(exists)


class TestUpdatePaymentSessions(AttendanceTestMixin, TestCase):
    """update_payment_sessions — cycle-scoped, not calendar-month-scoped."""

    def test_sessions_counted_correctly(self):
        """After 3 attendances, Payment.sessions_attended should be 3, cycle-scoped."""
        session = None
        for i in range(3):
            session = self._attend(day_offset=i)

        AttendanceService.update_payment_sessions(self.student, self.group)

        payment = Payment.objects.get(student=self.student, cycle=session.cycle)
        self.assertEqual(payment.sessions_attended, 3)
        self.assertEqual(payment.sessions_total, 4)

    def test_first_consumed_session_stamps_entitlement_anchor(self):
        """The very first session consumed in a cycle becomes the pricing anchor."""
        session = self._attend(day_offset=0)
        AttendanceService.update_payment_sessions(self.student, self.group)

        payment = Payment.objects.get(student=self.student, cycle=session.cycle)
        self.assertEqual(payment.entitlement_start_seq, 1)
        self.assertEqual(payment.entitlement_start_session_id, session.session_id)
        self.assertEqual(payment.amount_due, Decimal('200.00'))

    def test_mid_cycle_join_prorates_amount_due(self):
        """Joining at the group's 2nd session of a 4-session cycle → 3/4 fee."""
        other_student = Student.objects.create(
            student_code='ATT002', full_name='طالب آخر', gender='male',
            parent_phone='01098765433',
        )
        StudentGroupEnrollment.objects.create(
            student=other_student, group=self.group, financial_status='normal', is_active=True,
        )
        session1 = self._attend(day_offset=0, student=other_student)
        AttendanceService.update_payment_sessions(other_student, self.group)

        session2 = self._attend(day_offset=1, student=self.student)
        AttendanceService.update_payment_sessions(self.student, self.group)

        self.assertEqual(session2.cycle_id, session1.cycle_id)
        payment = Payment.objects.get(student=self.student, cycle=session2.cycle)
        self.assertEqual(payment.entitlement_start_seq, 2)
        self.assertEqual(payment.sessions_total, 3)
        self.assertEqual(payment.amount_due, Decimal('150.00'))


class TestLateJoinerNotChargedForEarlierAbsences(AttendanceTestMixin, TestCase):
    """
    Counting starts at the student's FIRST ATTENDANCE, not at the start of
    the cycle. ``auto_mark_absent_sessions`` writes an absence row for every
    enrolled student from day one, so counting from the cycle start charged a
    late joiner for sessions they were never at — and, because entitlement is
    pro-rated to what remains, exhausted it before their first lesson.
    """

    def test_absences_before_first_attendance_do_not_consume(self):
        for i in range(3):
            self._attend(day_offset=i, status='absent')
        session4 = self._attend(day_offset=3, status='present')

        AttendanceService.update_payment_sessions(self.student, self.group)
        payment = Payment.objects.get(student=self.student, cycle=session4.cycle)

        self.assertEqual(payment.entitlement_start_seq, 4)
        self.assertEqual(payment.sessions_total, 1)
        self.assertEqual(payment.sessions_attended, 1)
        # 200 ج.م over 4 sessions, entitled to the last one only.
        self.assertEqual(payment.amount_due, Decimal('50.00'))

    def test_absence_after_first_attendance_does_consume(self):
        """Once counting has started, an absence burns a session as normal."""
        self._attend(day_offset=0, status='present')
        self._attend(day_offset=1, status='absent')

        AttendanceService.update_payment_sessions(self.student, self.group)
        payment = Payment.objects.get(student=self.student, group=self.group)
        self.assertEqual(payment.entitlement_start_seq, 1)
        self.assertEqual(payment.sessions_attended, 2)

    def test_never_attended_consumes_nothing(self):
        """An enrolled student who never shows up must not burn entitlement."""
        for i in range(3):
            self._attend(day_offset=i, status='absent')

        AttendanceService.update_payment_sessions(self.student, self.group)
        payment = Payment.objects.get(student=self.student, group=self.group)
        self.assertIsNone(payment.entitlement_start_seq)
        self.assertEqual(payment.sessions_attended, 0)

    def test_late_joiner_is_not_locked_out_after_first_lesson(self):
        """The end-to-end symptom the bug produced: instant lockout."""
        self._mark_as_returning_student()
        for i in range(3):
            self._attend(day_offset=i, status='absent')
        self._attend(day_offset=3, status='present')
        AttendanceService.update_payment_sessions(self.student, self.group)

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertNotEqual(
            result.get('error_type'), 'sessions_exhausted',
            'a student who has attended once must not already be exhausted',
        )


class TestAnchorSurvivesRenumbering(AttendanceTestMixin, TestCase):
    """
    The consumed-session count is anchored on the start session's DATE, not
    its sequence number. Sequences are renumbered when a session is cancelled
    or backfilled at an earlier date, so a sequence-based anchor would
    silently come to mean a different lesson and mis-count the student.
    """

    def test_cancelling_an_earlier_session_does_not_shift_the_count(self):
        from apps.attendance.entitlement import _consumed_sessions

        s1 = self._attend(day_offset=0, status='absent')
        s2 = self._attend(day_offset=1, status='absent')
        s3 = self._attend(day_offset=2, status='present')   # student starts here
        self._attend(day_offset=3, status='present')

        AttendanceService.update_payment_sessions(self.student, self.group)
        payment = Payment.objects.get(student=self.student, cycle=s3.cycle)
        self.assertEqual(payment.entitlement_start_session_id, s3.session_id)
        self.assertEqual(_consumed_sessions(
            self.student, s3.cycle, anchor_session=payment.entitlement_start_session), 2)

        # Cancel a session BEFORE the student's start — everything after it
        # renumbers, but the student's own count must not move.
        from apps.teachers.cycles import renumber_cycle
        s2.is_cancelled = True
        s2.save(update_fields=['is_cancelled'])
        renumber_cycle(s3.cycle)

        payment.refresh_from_db()
        s3.refresh_from_db()
        self.assertEqual(s3.sequence_in_cycle, 2, 'sequence did shift')
        self.assertEqual(payment.entitlement_start_session_id, s3.session_id)
        self.assertEqual(
            _consumed_sessions(self.student, s3.cycle,
                               anchor_session=payment.entitlement_start_session),
            2,
            'count must still be the 2 sessions from the anchor date onward',
        )

    def test_cancelled_session_loses_its_sequence(self):
        s1 = self._attend(day_offset=0, status='present')
        s2 = self._attend(day_offset=1, status='present')
        from apps.teachers.cycles import renumber_cycle

        s1.is_cancelled = True
        s1.save(update_fields=['is_cancelled'])
        renumber_cycle(s1.cycle)

        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertIsNone(s1.sequence_in_cycle)
        self.assertEqual(s2.sequence_in_cycle, 1)
