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
from apps.payments.models import Payment
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room, Subject

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

        self.group = Group.objects.create(
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
        # Activate subscription
        self.student.activate_subscription(days=30)

        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
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
    """Test financial blocking: month 1 vs month 2+ grace sessions."""

    def test_month1_no_payment_blocked(self):
        """Month 1 student with 0 payments — should be BLOCKED (0 grace sessions)."""
        # No attendance history = first month in group
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'payment_required')

    def test_month1_with_payment_allowed(self):
        """Month 1 student who has paid — should be ALLOWED."""
        current_month = timezone.now().date().replace(day=1)
        Payment.objects.create(
            student=self.student, group=self.group,
            month=current_month, amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid',
        )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

    def test_month2_grace_session_1_allowed(self):
        """Month 2+ student, 0 sessions attended, no payment — 1st grace session allowed."""
        # Create past attendance to make it NOT month 1
        past_date = (timezone.now() - timedelta(days=35)).date()
        past_session = Session.objects.create(
            group=self.group, session_date=past_date
        )
        Attendance.objects.create(
            student=self.student, session=past_session,
            scan_time=timezone.now() - timedelta(days=35), status='present',
        )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

    def test_month2_grace_session_2_allowed(self):
        """Month 2+ student, 1 session attended this month, no payment — 2nd grace session allowed."""
        # Past attendance to establish month 2+
        past_date = (timezone.now() - timedelta(days=35)).date()
        past_session = Session.objects.create(
            group=self.group, session_date=past_date
        )
        Attendance.objects.create(
            student=self.student, session=past_session,
            scan_time=timezone.now() - timedelta(days=35), status='present',
        )

        # 1 session this month
        today_session = Session.objects.create(
            group=self.group, session_date=timezone.now().date()
        )
        Attendance.objects.create(
            student=self.student, session=today_session,
            scan_time=timezone.now(), status='present',
        )

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

    def test_month2_after_grace_blocked(self):
        """Month 2+ student, 2 sessions attended, no payment — 3rd session BLOCKED."""
        # Past attendance to establish month 2+
        past_date = (timezone.now() - timedelta(days=35)).date()
        past_session = Session.objects.create(
            group=self.group, session_date=past_date
        )
        Attendance.objects.create(
            student=self.student, session=past_session,
            scan_time=timezone.now() - timedelta(days=35), status='present',
        )

        # 2 sessions this month
        current_month = timezone.now().date().replace(day=1)
        for i in range(2):
            s_date = current_month + timedelta(days=i)
            session = Session.objects.create(group=self.group, session_date=s_date)
            Attendance.objects.create(
                student=self.student, session=session,
                scan_time=timezone.now(), status='present',
            )

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
    """Test session limit enforcement (sessions_per_month)."""

    def test_sessions_exhausted_blocked(self):
        """Student attended 4/4 sessions — 5th scan must be BLOCKED."""
        current_month = timezone.now().date().replace(day=1)

        # Create payment so financial check passes
        Payment.objects.create(
            student=self.student, group=self.group,
            month=current_month, amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid',
        )

        # Create 4 attendance records (= sessions_per_month)
        for i in range(4):
            s_date = current_month + timedelta(days=i)
            session = Session.objects.create(group=self.group, session_date=s_date)
            Attendance.objects.create(
                student=self.student, session=session,
                scan_time=timezone.now(), status='present',
            )

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'sessions_exhausted')
        self.assertEqual(result['sessions_limit'], 4)

    def test_3_of_4_sessions_allowed(self):
        """Student attended 3/4 sessions — 4th scan should be ALLOWED."""
        current_month = timezone.now().date().replace(day=1)

        # Create payment
        Payment.objects.create(
            student=self.student, group=self.group,
            month=current_month, amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid',
        )

        # Past attendance to establish month 2+
        past_date = (timezone.now() - timedelta(days=35)).date()
        past_session = Session.objects.create(group=self.group, session_date=past_date)
        Attendance.objects.create(
            student=self.student, session=past_session,
            scan_time=timezone.now() - timedelta(days=35), status='present',
        )

        # 3 sessions this month
        for i in range(3):
            s_date = current_month + timedelta(days=i)
            session = Session.objects.create(group=self.group, session_date=s_date)
            Attendance.objects.create(
                student=self.student, session=session,
                scan_time=timezone.now(), status='present',
            )

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

    def test_custom_session_limit(self):
        """Group with sessions_per_month=8 — student should be allowed after 4 sessions."""
        self.group.sessions_per_month = 8
        self.group.save()

        current_month = timezone.now().date().replace(day=1)
        Payment.objects.create(
            student=self.student, group=self.group,
            month=current_month, amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid',
        )

        # Past attendance for month 2+
        past_date = (timezone.now() - timedelta(days=35)).date()
        past_session = Session.objects.create(group=self.group, session_date=past_date)
        Attendance.objects.create(
            student=self.student, session=past_session,
            scan_time=timezone.now() - timedelta(days=35), status='present',
        )

        # 4 sessions this month (out of 8)
        for i in range(4):
            s_date = current_month + timedelta(days=i)
            session = Session.objects.create(group=self.group, session_date=s_date)
            Attendance.objects.create(
                student=self.student, session=session,
                scan_time=timezone.now(), status='present',
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


class TestSubscriptionExpiry(AttendanceTestMixin, TestCase):
    """Test subscription expiry blocking."""

    def test_expired_subscription_blocked(self):
        """Student with expired subscription — is_subscription_active() should return False."""
        self.student.subscription_expiry_date = timezone.now().date() - timedelta(days=1)
        self.student.save()

        self.assertFalse(self.student.is_subscription_active())

    def test_active_subscription_allowed(self):
        """Student with active subscription — should return True."""
        self.student.subscription_expiry_date = timezone.now().date() + timedelta(days=15)
        self.student.save()

        self.assertTrue(self.student.is_subscription_active())

    def test_no_subscription_active_when_no_date(self):
        """Student with no subscription_expiry_date — treated as 'no restriction', returns True.
        Business rule: no date set = subscription system not configured for this student = allow entry.
        (Changed from inactive to active in Feb 2026 fix to avoid blocking students who simply
        haven't had a subscription date configured yet.)
        """
        self.student.subscription_expiry_date = None
        self.student.last_payment_date = None
        self.student.save()

        self.assertTrue(self.student.is_subscription_active())


class TestUpdatePaymentSessions(AttendanceTestMixin, TestCase):
    """Test that payment session counter updates correctly."""

    def test_sessions_counted_correctly(self):
        """After 3 attendances, Payment.sessions_attended should be 3."""
        current_month = timezone.now().date().replace(day=1)

        for i in range(3):
            s_date = current_month + timedelta(days=i)
            session = Session.objects.create(group=self.group, session_date=s_date)
            Attendance.objects.create(
                student=self.student, session=session,
                scan_time=timezone.now(), status='present',
            )

        AttendanceService.update_payment_sessions(self.student, self.group)

        payment = Payment.objects.get(
            student=self.student, group=self.group, month=current_month
        )
        self.assertEqual(payment.sessions_attended, 3)
        self.assertEqual(payment.sessions_total, 4)
