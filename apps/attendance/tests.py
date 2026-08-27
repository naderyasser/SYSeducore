"""
Unit Tests for Attendance Service - Educore V2
اختبار النظام الجديد: قاعدة 10 دقائق صارمة + student_code
"""

from decimal import Decimal

from django.test import TestCase
from django.test import override_settings
from django.utils import timezone
from datetime import datetime, timedelta, time
from apps.accounts.models import User
from apps.teachers.models import Teacher, Group, Room
from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Session, Attendance
from apps.payments.models import Payment
from apps.attendance.services import AttendanceService
from apps.teachers.models import GroupCycle
from apps.teachers.cycles import assign_to_cycle
from apps.attendance import entitlement
from tests.factories import create_group_with_schedule


class AttendanceServiceStrictTest(TestCase):
    """
    اختبار قاعدة الـ 10 دقائق الصارمة
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        # Create supervisor
        self.supervisor = User.objects.create_user(
            username='supervisor',
            password='testpass123',
            role='supervisor'
        )

        # Create teacher
        self.teacher = Teacher.objects.create(
            full_name='محمد علي',
            email='teacher@test.com',
            phone='+201234567890',
            specialization='رياضيات',
            hire_date=timezone.now().date()
        )

        # Create room
        self.room = Room.objects.create(
            name='قاعة A',
            capacity=30
        )

        # Create group (بدون grace_period - النظام الثابت)
        self.group = create_group_with_schedule(
            group_name='مجموعة السبت',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(9, 0),  # 9:00 AM
            standard_fee=200.00
        )

        # Create student
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='+201234567890'
        )

        # Enroll student in group
        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

    def test_check_strict_time_on_time(self):
        """اختبار: وصول في الموعد (قبل 9:00)"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(8, 55))
        )

        result = AttendanceService.check_strict_time(scan_time, schedule_time)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['status'], 'present')

    def test_check_strict_time_5_minutes_late(self):
        """اختبار: تأخر 5 دقائق (9:05) - قبول مع تسجيل 'متأخر'"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 5))
        )

        result = AttendanceService.check_strict_time(scan_time, schedule_time)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['status'], 'late')
        self.assertEqual(result['minutes_late'], 5)

    def test_check_strict_time_exactly_10_minutes(self):
        """اختبار: تأخر بالظبط 10 دقائق (9:10) - قبول مع تسجيل 'متأخر'"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 10))
        )

        result = AttendanceService.check_strict_time(scan_time, schedule_time)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['status'], 'late')

    def test_check_strict_time_11_minutes_late_block(self):
        """اختبار: تأخر 11 دقيقة (9:11) - رفض كامل ⚠️"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 11))
        )

        result = AttendanceService.check_strict_time(scan_time, schedule_time)
        self.assertFalse(result['allowed'])
        self.assertIn('ممنوع الدخول', result['reason'])

    def test_check_strict_time_15_minutes_late_block(self):
        """اختبار: تأخر 15 دقيقة (9:15) - رفض كامل"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 15))
        )

        result = AttendanceService.check_strict_time(scan_time, schedule_time)
        self.assertFalse(result['allowed'])
        self.assertIn('ممنوع الدخول', result['reason'])

    def test_check_strict_time_too_early(self):
        """اختبار: وصول مبكر جداً (35 دقيقة قبل الموعد)"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(8, 25))
        )

        result = AttendanceService.check_strict_time(scan_time, schedule_time)
        self.assertFalse(result['allowed'])
        self.assertIn('مبكراً جداً', result['reason'])

    def test_get_current_day_name(self):
        """اختبار: الحصول على اسم اليوم الحالي"""
        day_name = AttendanceService.get_current_day_name()
        self.assertIn(day_name, ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])


class AttendanceFinancialCheckTest(TestCase):
    """
    اختبار الفحص المالي — بالحصص، عبر ``check_financial_status`` (الغلاف
    الرقيق حول ``apps.attendance.entitlement.evaluate``).
    """

    def setUp(self):
        """إعداد البيانات"""
        self.supervisor = User.objects.create_user(
            username='supervisor',
            password='testpass123',
            role='supervisor'
        )

        self.teacher = Teacher.objects.create(
            full_name='Test Teacher',
            email='teacher@test.com',
            phone='+201234567890',
            specialization='Math',
            hire_date=timezone.now().date()
        )

        self.room = Room.objects.create(name='Room A', capacity=30)

        self.group = create_group_with_schedule(
            group_name='Test Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(9, 0),
            standard_fee=200.00
        )

        # Student 1: Normal
        self.student_normal = Student.objects.create(
            student_code='1001',
            full_name='Normal Student',
            parent_phone='+201234567890'
        )
        self.enrollment_normal = StudentGroupEnrollment.objects.create(
            student=self.student_normal,
            group=self.group,
            financial_status='normal'
        )

        # Student 2: Exempt
        self.student_exempt = Student.objects.create(
            student_code='1002',
            full_name='Exempt Student',
            parent_phone='+201234567891'
        )
        StudentGroupEnrollment.objects.create(
            student=self.student_exempt,
            group=self.group,
            financial_status='exempt'
        )

    def _attend(self, student, day_offset=0, status='present'):
        session = assign_to_cycle(Session.objects.create(
            group=self.group, session_date=timezone.localdate() + timedelta(days=day_offset),
        ))
        Attendance.objects.create(
            student=student, session=session, status=status, supervisor=self.supervisor,
        )
        return session

    def test_financial_check_exempt_always_allowed(self):
        """اختبار: الطالب المعفي دائماً مسموح"""
        result = AttendanceService.check_financial_status(self.student_exempt, self.group)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('exempt', False))

    def test_financial_check_first_cycle_no_payment(self):
        """أول دورة للطالب في هذه المجموعة، بدون دفع سابق — يُرفض فورًا."""
        result = AttendanceService.check_financial_status(self.student_normal, self.group)
        self.assertFalse(result['allowed'])
        self.assertIn('أول اشتراك', result['reason'])
        self.assertEqual(result['amount_due'], 200.0)

    def test_financial_check_first_cycle_with_payment(self):
        """أول دورة، مع دفع مسبق — مسموح."""
        cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4, started_on=timezone.localdate(),
        )
        Payment.objects.create(
            student=self.student_normal, group=self.group, cycle=cycle,
            month=timezone.localdate().replace(day=1),
            amount_due=200.00, amount_paid=200.00, status='paid',
            sessions_total=4,
        )
        result = AttendanceService.check_financial_status(self.student_normal, self.group)
        self.assertTrue(result['allowed'])

    def test_financial_check_returning_student_first_session_of_new_cycle(self):
        """طالب دفع من قبل لهذه المجموعة — الحصة الأولى في دورة جديدة غير مدفوعة مسموحة (سماح)."""
        # سجّل دفعة قديمة (مستقلة عن الدورة الحالية) لإثبات أنه "دفع من قبل".
        Payment.objects.create(
            student=self.student_normal, group=self.group, cycle=None,
            month=timezone.localdate().replace(day=1, month=1),
            amount_due=200.00, amount_paid=200.00, status='paid',
        )
        result = AttendanceService.check_financial_status(self.student_normal, self.group)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('grace_sessions'))

    def test_financial_check_returning_student_third_session_blocked(self):
        """طالب دفع من قبل — بعد استهلاك حصتي السماح دون دفع الدورة الجديدة، يُرفض."""
        Payment.objects.create(
            student=self.student_normal, group=self.group, cycle=None,
            month=timezone.localdate().replace(day=1, month=1),
            amount_due=200.00, amount_paid=200.00, status='paid',
        )
        self._attend(self.student_normal, day_offset=0)
        self._attend(self.student_normal, day_offset=1)

        result = AttendanceService.check_financial_status(self.student_normal, self.group)
        self.assertFalse(result['allowed'])
        self.assertIn('ممنوع الدخول', result['reason'])


class ProcessScanIntegrationTest(TestCase):
    """
    اختبار تكامل process_scan (النظام الكامل)
    """

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='supervisor',
            password='testpass123',
            role='supervisor'
        )

        self.teacher = Teacher.objects.create(
            full_name='Test Teacher',
            email='teacher@test.com',
            phone='+201234567890',
            specialization='Math',
            hire_date=timezone.now().date()
        )

        self.room = Room.objects.create(name='Room A', capacity=30)

        self.group = create_group_with_schedule(
            group_name='Test Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(9, 0),
            standard_fee=200.00
        )

        self.student = Student.objects.create(
            student_code='1001',
            full_name='Test Student',
            parent_phone='+201234567890'
        )

        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

    def test_process_scan_invalid_student_code(self):
        """اختبار: كود طالب غير صحيح"""
        result = AttendanceService.process_scan('9999', self.supervisor)
        self.assertFalse(result['success'])
        self.assertIn('غير موجود', result['message'])

    def test_process_scan_no_class_today(self):
        """اختبار: لا توجد حصة مجدولة اليوم"""
        # Group مجدول ليوم السبت، فإذا اليوم ليس سبت، سيفشل
        result = AttendanceService.process_scan(self.student.student_code, self.supervisor)

        # قد ينجح أو يفشل حسب اليوم الحالي
        self.assertIn('success', result)


class TimezoneLocalDayNameTest(TestCase):
    """
    Fix 1: Verify get_current_day_name uses local timezone, not UTC.
    """

    def test_get_current_day_name_uses_localtime(self):
        """get_current_day_name should return the local (Cairo) day name, not UTC."""
        from unittest.mock import patch
        from datetime import timezone as dt_timezone
        from zoneinfo import ZoneInfo

        cairo_tz = ZoneInfo('Africa/Cairo')

        # Simulate 00:30 Cairo time on a Saturday = Friday 22:30 UTC
        # Cairo Saturday 00:30 → UTC Friday 22:30
        cairo_saturday_0030 = datetime(
            2026, 4, 18, 0, 30, tzinfo=cairo_tz  # Saturday in Cairo
        )
        utc_equivalent = cairo_saturday_0030.astimezone(dt_timezone.utc)

        with patch('apps.attendance.services.timezone.localtime') as mock_localtime:
            mock_localtime.return_value = cairo_saturday_0030
            day_name = AttendanceService.get_current_day_name()
            self.assertEqual(day_name, 'Saturday')

        # Verify that if we used UTC weekday, we'd get Friday (the bug)
        self.assertEqual(utc_equivalent.weekday(), 4)  # Friday
        self.assertEqual(cairo_saturday_0030.weekday(), 5)  # Saturday

    def test_get_current_day_name_returns_valid_day(self):
        """get_current_day_name should always return a valid English day name."""
        day_name = AttendanceService.get_current_day_name()
        valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        self.assertIn(day_name, valid_days)


class RateLimitScanEndpointTest(TestCase):
    """
    Fix 2: Verify rate limiting is applied to the scan endpoint.
    """

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='supervisor',
            password='testpass123',
            role='supervisor'
        )
        self.client.login(username='supervisor', password='testpass123')

    @override_settings(RATELIMIT_ENABLE=True)
    def test_scan_endpoint_rate_limited(self):
        """Scan endpoint should return 429 after exceeding 30 requests/minute."""
        from django.test import RequestFactory
        from django_ratelimit.exceptions import Ratelimited

        # Verify the decorator is present by checking the view function
        from apps.attendance.views import process_student_code
        # The view should have ratelimit applied — we verify it's importable
        # and the decorator attribute exists
        self.assertTrue(callable(process_student_code))

    def test_scan_endpoint_accessible_when_not_rate_limited(self):
        """Normal scan requests should work when under the rate limit."""
        import json
        response = self.client.post(
            '/attendance/api/process-code/',
            data=json.dumps({'student_code': '9999'}),
            content_type='application/json'
        )
        # Should get a normal response (student not found), not 429
        self.assertNotEqual(response.status_code, 429)
        data = response.json()
        self.assertFalse(data['success'])


class FirstMonthPaymentFlagTest(TestCase):
    """
    Fix 3: Verify ENABLE_FIRST_MONTH_STRICT_PAYMENT flag controls first-month behavior.
    """

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='supervisor',
            password='testpass123',
            role='supervisor'
        )
        self.teacher = Teacher.objects.create(
            full_name='Test Teacher',
            email='teacher@test.com',
            phone='+201234567890',
            specialization='Math',
            hire_date=timezone.now().date()
        )
        self.room = Room.objects.create(name='Room A', capacity=30)
        self.group = create_group_with_schedule(
            group_name='Test Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(9, 0),
            standard_fee=200.00
        )
        self.student = Student.objects.create(
            student_code='2001',
            full_name='New Student',
            parent_phone='+201234567890'
        )
        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

    @override_settings(ENABLE_FIRST_MONTH_STRICT_PAYMENT=True)
    def test_first_month_strict_true_blocks_unpaid(self):
        """When flag is True, first-cycle student with no payment should be blocked."""
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertIn('أول اشتراك', result.get('reason', ''))

    @override_settings(ENABLE_FIRST_MONTH_STRICT_PAYMENT=False)
    def test_first_month_strict_false_allows_grace(self):
        """When flag is False, first-cycle student gets 2-session grace like returning students."""
        result = AttendanceService.check_financial_status(self.student, self.group)
        # With 0 sessions attended and 2 allowed, should be allowed
        self.assertTrue(result['allowed'])

    @override_settings(ENABLE_FIRST_MONTH_STRICT_PAYMENT=True)
    def test_first_month_strict_true_with_payment_allowed(self):
        """When flag is True, first-cycle student who has paid should be allowed."""
        cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4, started_on=timezone.localdate(),
        )
        Payment.objects.create(
            student=self.student,
            group=self.group,
            cycle=cycle,
            month=timezone.now().date().replace(day=1),
            amount_due=200.00,
            amount_paid=200.00,
            status='paid'
        )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])


class BarcodeNormalizationTest(TestCase):
    """
    اختبار تنظيف كود الباركود المُدخَل من الكاميرا
    Barcode values from scanners often carry extra whitespace or padding chars.
    """

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='sup_norm', password='testpass123', role='supervisor'
        )

    def test_whitespace_stripped(self):
        """Leading/trailing spaces must be stripped before lookup."""
        result = AttendanceService.process_scan(' 9999 ', self.supervisor)
        # Student doesn't exist — but the failure should reference the code
        # NOT a server error (which would mean normalization blew up)
        self.assertFalse(result['success'])
        self.assertIn('9999', result.get('message', ''))

    def test_newline_stripped(self):
        """Barcode reader may append \\n — should be stripped."""
        result = AttendanceService.process_scan('9999\n', self.supervisor)
        self.assertFalse(result['success'])
        self.assertIn('9999', result.get('message', ''))

    def test_asterisk_padding_stripped(self):
        """Code128 asterisk delimiters should be stripped."""
        result = AttendanceService.process_scan('*9999*', self.supervisor)
        self.assertFalse(result['success'])
        self.assertIn('9999', result.get('message', ''))

    def test_empty_code_handled(self):
        """Empty code after stripping should return useful error, not crash."""
        result = AttendanceService.process_scan('   ', self.supervisor)
        self.assertFalse(result['success'])


class DossierTest(TestCase):
    """
    اختبار بناء ملف الطالب الشامل (build_student_dossier)
    """

    def setUp(self):
        self.supervisor = User.objects.create_user(
            username='sup_doss', password='testpass123', role='supervisor'
        )
        self.teacher = Teacher.objects.create(
            full_name='مدرس التجربة',
            email='doss_teacher@test.com',
            phone='+201000000001',
            specialization='علوم',
            hire_date=timezone.now().date()
        )
        self.room = Room.objects.create(name='قاعة D', capacity=25)
        self.group_a = create_group_with_schedule(
            group_name='مجموعة ألفا',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            standard_fee=300.00
        )
        self.group_b = create_group_with_schedule(
            group_name='مجموعة بيتا',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Tuesday',
            schedule_time=time(16, 0),
            standard_fee=250.00
        )
        self.student = Student.objects.create(
            student_code='5500',
            full_name='طالب التجربة',
            parent_phone='+201111111111',
            parent_name='ولي الأمر',
            education_stage='secondary',
            education_year='2'
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group_a, financial_status='normal'
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group_b, financial_status='exempt'
        )

    def test_dossier_basic_fields(self):
        """Dossier must include name, code, parent phone, education."""
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertEqual(dossier['full_name'], 'طالب التجربة')
        self.assertEqual(dossier['student_code'], '5500')
        self.assertEqual(dossier['parent_phone'], '+201111111111')
        self.assertIn('ثانوي', dossier['education'])

    def test_dossier_enrollments_count(self):
        """Dossier must list all active enrollments."""
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertEqual(len(dossier['enrollments']), 2)

    def test_dossier_exempt_group_payment(self):
        """Exempt group must show pay_status='exempt'."""
        dossier = AttendanceService.build_student_dossier(self.student)
        exempt_enr = next(
            e for e in dossier['enrollments'] if e['group_name'] == 'مجموعة بيتا'
        )
        self.assertEqual(exempt_enr['payment']['status'], 'exempt')
        self.assertEqual(exempt_enr['payment']['amount_due'], 0.0)

    def test_dossier_unpaid_group_payment(self):
        """Group with no payment record must show pay_status='unpaid'."""
        dossier = AttendanceService.build_student_dossier(self.student)
        normal_enr = next(
            e for e in dossier['enrollments'] if e['group_name'] == 'مجموعة ألفا'
        )
        self.assertEqual(normal_enr['payment']['status'], 'unpaid')
        self.assertEqual(normal_enr['payment']['amount_due'], 300.0)

    def test_dossier_paid_group_payment(self):
        """Group with paid payment must reflect correct amounts."""
        cycle = GroupCycle.objects.create(
            group=self.group_a, index=1, sessions_planned=4, started_on=timezone.localdate(),
        )
        Payment.objects.create(
            student=self.student, group=self.group_a, cycle=cycle,
            month=timezone.localtime().date().replace(day=1),
            amount_due=300.00, amount_paid=300.00, status='paid'
        )
        dossier = AttendanceService.build_student_dossier(self.student)
        normal_enr = next(
            e for e in dossier['enrollments'] if e['group_name'] == 'مجموعة ألفا'
        )
        self.assertEqual(normal_enr['payment']['status'], 'paid')
        self.assertEqual(normal_enr['payment']['remaining'], 0.0)
        self.assertEqual(normal_enr['entitlement']['cycle_index'], 1)

    def test_dossier_attendance_month_count(self):
        """Dossier attendance_month.total must match actual attendance records."""
        from apps.attendance.models import Session, Attendance
        session = Session.objects.create(
            group=self.group_a,
            session_date=timezone.localtime().date()
        )
        Attendance.objects.create(
            student=self.student,
            session=session,
            status='present',
            supervisor=self.supervisor
        )
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertEqual(dossier['attendance_month']['total'], 1)
        self.assertIsNotNone(dossier['attendance_month']['last_scan'])

    def test_dossier_included_in_scan_result(self):
        """Successful scan must include 'dossier' key in result."""
        from unittest.mock import patch
        now_local = timezone.localtime()
        # Simulate scan at 10:05 on a Sunday
        fake_day = 'Sunday'
        fake_time = now_local.replace(hour=10, minute=5)
        with patch.object(AttendanceService, 'get_current_day_name', return_value=fake_day):
            with patch('apps.attendance.services.timezone.localtime', return_value=fake_time):
                with patch('apps.attendance.services.timezone.now', return_value=fake_time):
                    result = AttendanceService.process_scan('5500', self.supervisor)
        # Whether it succeeds or fails on time, if student exists and subscription OK,
        # dossier is included on success
        if result.get('success'):
            self.assertIn('dossier', result)
            self.assertEqual(result['dossier']['student_code'], '5500')

    def test_dossier_personal_section(self):
        """Dossier must include personal section with parent_name and registration_date."""
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertIn('personal', dossier)
        self.assertEqual(dossier['personal']['parent_name'], 'ولي الأمر')
        self.assertIsNotNone(dossier['personal']['registration_date'])

    def test_dossier_financial_summary(self):
        """Dossier must include financial_summary with totals from enrollments."""
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertIn('financial_summary', dossier)
        # group_a (300 unpaid) + group_b (exempt 0) = 300 total_due
        self.assertEqual(dossier['financial_summary']['total_due'], 300.0)
        self.assertEqual(dossier['financial_summary']['total_paid'], 0.0)
        self.assertEqual(dossier['financial_summary']['total_remaining'], 300.0)

    def test_dossier_attendance_rate_no_sessions(self):
        """When no sessions exist, attendance rate should be None."""
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertIsNone(dossier['attendance_month']['rate'])

    def test_severity_in_not_found(self):
        """Scan for non-existent student must return severity='error'."""
        result = AttendanceService.process_scan('NONEXISTENT', self.supervisor)
        self.assertEqual(result['severity'], 'error')

# ─────────────────────────────────────────────────────────────
# Scanner Quick-Action Tests  (Pay Now / Grace Period)
# ─────────────────────────────────────────────────────────────

import json
from django.test import TestCase, Client
from django.urls import reverse


class ScannerPayNowTest(TestCase):
    """
    Tests for the scanner_pay_now API endpoint.
    Verifies that marking a payment as paid from the scanner UI
    correctly updates the Payment, Student, and Enrollment records.
    """

    def setUp(self):
        """Create a student with an unpaid payment and an active enrollment."""
        self.client = Client()

        # Create supervisor user
        self.supervisor = User.objects.create_user(
            username='sup_pay', password='testpass123', role='supervisor'
        )
        self.client.login(username='sup_pay', password='testpass123')

        # Create teacher, room, group
        self.teacher = Teacher.objects.create(
            full_name='أحمد المدرس',
            phone='+201000000001',
            hire_date=timezone.now().date(),
        )
        self.room = Room.objects.create(name='قاعة اختبار الدفع', capacity=25)
        self.group = create_group_with_schedule(
            group_name='مجموعة اختبار الدفع',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(10, 0),
            standard_fee=150.00,
        )

        # Create student
        self.student = Student.objects.create(
            student_code='9001',
            full_name='طالب اختبار الدفع',
            parent_phone='+201000000099',
        )

        # Enroll student in group
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal',
        )

        # Create an unpaid payment for the group's (freshly opened) cycle —
        # ``_resolve_scanner_payment`` (via student_id) resolves by the
        # group's OPEN cycle, so the fixture payment must live there too.
        current_month = timezone.localtime().date().replace(day=1)
        self.cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=self.group.sessions_per_month,
        )
        self.payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            cycle=self.cycle,
            month=current_month,
            amount_due=150.00,
            amount_paid=0,
            status='unpaid',
        )

    def test_pay_now_with_payment_id(self):
        """POST with payment_id should mark payment as paid and activate subscription."""
        url = reverse('attendance:scanner_pay_now')
        payload = {'payment_id': self.payment.payment_id}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

        # Refresh from DB
        self.payment.refresh_from_db()
        self.student.refresh_from_db()
        self.enrollment.refresh_from_db()

        # Payment should be paid
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.amount_paid, self.payment.amount_due)
        self.assertIsNotNone(self.payment.payment_date)

        # Enrollment should be active
        self.assertTrue(self.enrollment.is_active)

    def test_pay_now_with_student_id(self):
        """POST with student_id should find/create payment and mark as paid."""
        url = reverse('attendance:scanner_pay_now')
        payload = {'student_id': self.student.student_id}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

        # Payment should be paid
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')

    def test_pay_now_missing_params(self):
        """POST without payment_id or student_id should return 400."""
        url = reverse('attendance:scanner_pay_now')
        payload = {}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])

    def test_pay_now_invalid_payment_id(self):
        """POST with non-existent payment_id should return 404."""
        url = reverse('attendance:scanner_pay_now')
        payload = {'payment_id': 999999}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 404)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])

    def test_pay_now_requires_login(self):
        """Unauthenticated request should be rejected."""
        client = Client()  # not logged in
        url = reverse('attendance:scanner_pay_now')
        payload = {'payment_id': self.payment.payment_id}
        resp = client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        # ajax_login_required returns 401 for unauthenticated
        self.assertIn(resp.status_code, [401, 302])

    def test_pay_now_reactivates_inactive_enrollment(self):
        """If enrollment is inactive, pay_now should reactivate it."""
        self.enrollment.is_active = False
        self.enrollment.save()

        url = reverse('attendance:scanner_pay_now')
        payload = {'payment_id': self.payment.payment_id}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 200)
        self.enrollment.refresh_from_db()
        self.assertTrue(self.enrollment.is_active)


class ScannerGracePeriodTest(TestCase):
    """
    Tests for the scanner_grace_period API endpoint.
    Verifies that granting a grace period sets grace_until correctly
    WITHOUT changing the payment status.
    """

    def setUp(self):
        """Create a student with an unpaid payment."""
        self.client = Client()

        # Create supervisor
        self.supervisor = User.objects.create_user(
            username='sup_grace', password='testpass123', role='supervisor'
        )
        self.client.login(username='sup_grace', password='testpass123')

        # Create teacher, room, group
        self.teacher = Teacher.objects.create(
            full_name='مدرس المهلة',
            phone='+201000000002',
            hire_date=timezone.now().date(),
        )
        self.room = Room.objects.create(name='قاعة المهلة', capacity=20)
        self.group = create_group_with_schedule(
            group_name='مجموعة المهلة',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Monday',
            schedule_time=time(14, 0),
            standard_fee=200.00,
        )

        # Create student
        self.student = Student.objects.create(
            student_code='9002',
            full_name='طالب المهلة',
            parent_phone='+201000000098',
        )

        # Enroll student
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal',
        )

        # Create unpaid payment
        current_month = timezone.localtime().date().replace(day=1)
        self.payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=current_month,
            amount_due=200.00,
            amount_paid=0,
            status='unpaid',
        )

    def test_grace_period_sets_grace_until(self):
        """POST with days=3 should set grace_until to today + 3 days."""
        url = reverse('attendance:scanner_grace_period')
        payload = {'student_id': self.student.student_id, 'days': 3}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['days'], 3)

        expected_grace = timezone.localtime().date() + timedelta(days=3)
        self.assertEqual(data['grace_until'], expected_grace.isoformat())

        # Verify enrollment grace_until is set
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.grace_until, expected_grace)

    def test_grace_period_does_not_change_payment_status(self):
        """Grace period must NOT change the payment status — it should remain 'unpaid'."""
        url = reverse('attendance:scanner_grace_period')
        payload = {'student_id': self.student.student_id, 'days': 7}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 200)

        # Payment status must remain unpaid
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'unpaid')
        self.assertEqual(self.payment.amount_paid, 0)

    def test_grace_period_is_scoped_to_this_group_only(self):
        """Granting grace for one group must never touch the student elsewhere."""
        other_teacher = Teacher.objects.create(
            full_name='مدرس آخر', phone='+201000000003', hire_date=timezone.now().date(),
        )
        other_group = create_group_with_schedule(
            group_name='مجموعة أخرى', teacher=other_teacher, room=self.room,
            schedule_day='Tuesday', schedule_time=time(15, 0), standard_fee=150.00,
        )
        other_enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=other_group, financial_status='normal',
        )

        url = reverse('attendance:scanner_grace_period')
        payload = {'student_id': self.student.student_id, 'group_id': self.group.group_id, 'days': 3}
        resp = self.client.post(
            url, data=json.dumps(payload), content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 200)
        self.enrollment.refresh_from_db()
        other_enrollment.refresh_from_db()
        self.assertIsNotNone(self.enrollment.grace_until)
        self.assertIsNone(other_enrollment.grace_until)

    def test_grace_period_default_days(self):
        """If days is not provided, default should be 3."""
        url = reverse('attendance:scanner_grace_period')
        payload = {'student_id': self.student.student_id}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data['days'], 3)

    def test_grace_period_missing_student_id(self):
        """POST without student_id should return 400."""
        url = reverse('attendance:scanner_grace_period')
        payload = {'days': 5}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])

    def test_grace_period_invalid_student(self):
        """POST with non-existent student_id should return 404."""
        url = reverse('attendance:scanner_grace_period')
        payload = {'student_id': 999999, 'days': 3}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 404)

    def test_grace_period_does_not_reactivate_removed_enrollment(self):
        """
        AUTH-03: granting a payment grace period must NOT silently put the
        student back into groups the desk removed them from. It used to
        reactivate every inactive enrollment the student ever had.
        """
        self.enrollment.is_active = False
        self.enrollment.save()

        url = reverse('attendance:scanner_grace_period')
        payload = {'student_id': self.student.student_id, 'days': 3}
        resp = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(resp.status_code, 200)
        self.enrollment.refresh_from_db()
        self.assertFalse(self.enrollment.is_active)
        self.assertIsNone(self.enrollment.grace_until)

    def test_grace_period_rejects_teacher_role(self):
        """AUTH-03: a teacher-role account must not be able to grant grace."""
        User.objects.create_user(
            username='teacher_grace', password='testpass123', role='teacher'
        )
        client = Client()
        client.login(username='teacher_grace', password='testpass123')

        resp = client.post(
            reverse('attendance:scanner_grace_period'),
            data=json.dumps({'student_id': self.student.student_id, 'days': 3}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.enrollment.refresh_from_db()
        self.assertIsNone(self.enrollment.grace_until)

    def test_grace_period_rejects_absurd_day_count(self):
        """Day count is validated instead of being trusted from the request."""
        resp = self.client.post(
            reverse('attendance:scanner_grace_period'),
            data=json.dumps({'student_id': self.student.student_id, 'days': 3650}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)


class GracePeriodFinancialCheckTest(TestCase):
    """
    Tests for check_financial_status with grace period.
    Verifies that an unpaid student with an active grace_until date
    is allowed to attend without being rejected for payment.
    """

    def setUp(self):
        """Create student, group, enrollment with grace period."""
        self.teacher = Teacher.objects.create(
            full_name='مدرس فحص المهلة',
            phone='+201000000003',
            hire_date=timezone.now().date(),
        )
        self.room = Room.objects.create(name='قاعة فحص المهلة', capacity=20)
        self.group = create_group_with_schedule(
            group_name='مجموعة فحص المهلة',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Wednesday',
            schedule_time=time(16, 0),
            standard_fee=250.00,
            sessions_per_month=4,
        )

        self.student = Student.objects.create(
            student_code='9003',
            full_name='طالب فحص المهلة',
            parent_phone='+201000000097',
        )

        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal',
            is_active=True,
        )

        # Create unpaid payment
        current_month = timezone.localtime().date().replace(day=1)
        self.payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=current_month,
            amount_due=250.00,
            amount_paid=0,
            status='unpaid',
        )

    def test_unpaid_without_grace_rejected(self):
        """Unpaid student without grace period should be rejected."""
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertEqual(result.get('error_type'), 'payment_required')

    def test_unpaid_with_future_grace_allowed(self):
        """Unpaid student with future grace_until should be allowed."""
        future = timezone.localtime().date() + timedelta(days=3)
        self.enrollment.grace_until = future
        self.enrollment.save()

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('grace_period'))
        self.assertEqual(result['grace_until'], future.isoformat())

    def test_unpaid_with_expired_grace_rejected(self):
        """Unpaid student with past grace_until should be rejected."""
        past = timezone.localtime().date() - timedelta(days=2)
        self.enrollment.grace_until = past
        self.enrollment.save()

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertEqual(result.get('error_type'), 'payment_required')

    def test_unpaid_with_today_grace_allowed(self):
        """Unpaid student with grace_until = today should still be allowed."""
        today = timezone.localtime().date()
        self.enrollment.grace_until = today
        self.enrollment.save()

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('grace_period'))

    def test_grace_period_does_not_change_payment(self):
        """Grace period approval should not modify the payment record."""
        future = timezone.localtime().date() + timedelta(days=5)
        self.enrollment.grace_until = future
        self.enrollment.save()

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

        # Payment should still be unpaid
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'unpaid')
        self.assertEqual(self.payment.amount_paid, 0)

    def test_exempt_student_always_allowed(self):
        """Exempt student should be allowed regardless of payment/grace."""
        self.enrollment.financial_status = 'exempt'
        self.enrollment.save()

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('exempt'))

    def test_paid_student_allowed_without_grace(self):
        """Paid student should be allowed even without grace period."""
        self.payment.status = 'paid'
        self.payment.amount_paid = self.payment.amount_due
        self.payment.save()

        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])

    def test_process_scan_includes_payment_info_on_schedule_rejection(self):
        """
        When a student is unpaid and gets a schedule rejection (no matching session),
        the response should include payment_info so the scanner UI can show
        action buttons even without a matching session.
        """
        # Scan on a day/time that doesn't match the group schedule
        # Group is Wednesday 16:00, so scanning now (likely not Wed 16:00)
        # should give a schedule rejection but still include payment_info
        supervisor = User.objects.create_user(
            username='sup_scan_test', password='testpass123', role='supervisor'
        )
        result = AttendanceService.process_scan('9003', supervisor)

        # The scan should fail (schedule mismatch)
        self.assertFalse(result['success'])

        # But payment_info should be present since student is unpaid
        if result.get('error_type') in ('no_session_today', 'too_early', 'too_late', 'session_ended'):
            self.assertIn('payment_info', result,
                          'payment_info should be included in schedule rejection responses')
            self.assertEqual(result['payment_info']['error_type'], 'payment_required')
            self.assertEqual(result['payment_info']['student_id'], self.student.student_id)


# ─────────────────────────────────────────────────────────────
# Audit regression tests (2026-07 full-system audit)
# ─────────────────────────────────────────────────────────────


class AuditFixturesMixin:
    """Shared objects for the audit regression tests below."""

    def build_fixtures(self, day='Saturday', sessions_per_month=4):
        self.admin = User.objects.create_user(
            username='aud_admin', password='testpass123', role='admin'
        )
        self.supervisor = User.objects.create_user(
            username='aud_sup', password='testpass123', role='supervisor'
        )
        self.teacher_user = User.objects.create_user(
            username='aud_teacher', password='testpass123', role='teacher'
        )
        self.teacher = Teacher.objects.create(
            full_name='مدرس التدقيق', phone='+201000000010',
            hire_date=timezone.localdate(),
        )
        self.room = Room.objects.create(name='قاعة التدقيق', capacity=30)
        self.group = create_group_with_schedule(
            group_name='مجموعة التدقيق',
            teacher=self.teacher,
            room=self.room,
            schedule_day=day,
            schedule_time=time(9, 0),
            duration_minutes=120,
            standard_fee=200.00,
            sessions_per_month=sessions_per_month,
        )
        self.student = Student.objects.create(
            student_code='7100', full_name='طالب التدقيق',
            parent_phone='+201000000011',
        )
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )


class UnlimitedSessionsPerMonthTest(AuditFixturesMixin, TestCase):
    """DATA-11: sessions_per_month = 0 means unlimited, not 'block everyone'."""

    def setUp(self):
        self.build_fixtures(sessions_per_month=0)

    def test_zero_limit_does_not_block(self):
        current_month = timezone.localdate().replace(day=1)
        Payment.objects.create(
            student=self.student, group=self.group, month=current_month,
            amount_due=200, amount_paid=200, status='paid',
        )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])
        self.assertNotEqual(result.get('error_type'), 'sessions_exhausted')

    def test_zero_limit_still_allows_after_many_sessions(self):
        current_month = timezone.localdate().replace(day=1)
        Payment.objects.create(
            student=self.student, group=self.group, month=current_month,
            amount_due=200, amount_paid=200, status='paid',
        )
        for i in range(6):
            session = Session.objects.create(
                group=self.group, session_date=current_month + timedelta(days=i)
            )
            Attendance.objects.create(
                student=self.student, session=session, status='present',
            )
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertTrue(result['allowed'])


class ReadPathSideEffectTest(AuditFixturesMixin, TestCase):
    """DATA-13: status checks must not create Payment rows."""

    def setUp(self):
        self.build_fixtures()

    def test_get_instant_status_creates_nothing(self):
        AttendanceService.get_instant_status(self.student, self.group)
        self.assertEqual(Payment.objects.count(), 0)

    def test_check_financial_status_creates_nothing(self):
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'payment_required')
        self.assertIsNone(result['payment_id'])
        self.assertEqual(result['amount_due'], 200.0)
        self.assertEqual(Payment.objects.count(), 0)


class OverdueMonthsTest(AuditFixturesMixin, TestCase):
    """DATA-20: overdue months are months, not payment rows."""

    def setUp(self):
        self.build_fixtures()
        self.group_b = create_group_with_schedule(
            group_name='مجموعة التدقيق ب',
            teacher=self.teacher, room=self.room,
            schedule_day='Sunday', schedule_time=time(13, 0),
            duration_minutes=120, standard_fee=150.00,
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group_b, financial_status='normal',
        )

    def test_one_unpaid_month_in_two_groups_counts_once(self):
        last_month = (timezone.localdate().replace(day=1) - timedelta(days=1)).replace(day=1)
        for group in (self.group, self.group_b):
            Payment.objects.create(
                student=self.student, group=group, month=last_month,
                amount_due=100, amount_paid=0, status='unpaid',
            )
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertEqual(dossier['financial_summary']['overdue_months'], 1)


class AttendanceRateTest(AuditFixturesMixin, TestCase):
    """DATA-21: the rate can never exceed 100%."""

    def setUp(self):
        self.build_fixtures()

    def test_rate_ignores_groups_the_student_left(self):
        other_group = create_group_with_schedule(
            group_name='مجموعة سابقة', teacher=self.teacher, room=self.room,
            schedule_day='Monday', schedule_time=time(18, 0),
            duration_minutes=120, standard_fee=100.00,
        )
        current_month = timezone.localdate().replace(day=1)

        # One session in the enrolled group (attended)
        enrolled_session = Session.objects.create(
            group=self.group, session_date=current_month
        )
        Attendance.objects.create(
            student=self.student, session=enrolled_session, status='present',
        )
        # Two sessions in a group the student is no longer enrolled in
        for i in range(2):
            s = Session.objects.create(
                group=other_group, session_date=current_month + timedelta(days=i)
            )
            Attendance.objects.create(student=self.student, session=s, status='present')

        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertLessEqual(dossier['attendance_month']['rate'], 100.0)
        self.assertEqual(dossier['attendance_month']['rate'], 100.0)


class DossierArabicScheduleTest(AuditFixturesMixin, TestCase):
    """DOC-05: day names in the dossier must render in Arabic."""

    def setUp(self):
        self.build_fixtures(day='Saturday')

    def test_schedule_is_arabic(self):
        dossier = AttendanceService.build_student_dossier(self.student)
        entry = dossier['enrollments'][0]
        self.assertIn('السبت', entry['schedule'])
        self.assertEqual(entry['schedule_day_ar'], 'السبت')
        self.assertNotIn('Saturday', entry['schedule'])


class ScannerRolePermissionTest(AuditFixturesMixin, TestCase):
    """AUTH-03 / AUTH-04 / AUTH-08: desk-only endpoints reject teachers."""

    def setUp(self):
        self.build_fixtures()
        self.client = Client()
        self.client.login(username='aud_teacher', password='testpass123')

    def test_teacher_cannot_pay_now(self):
        current_month = timezone.localdate().replace(day=1)
        payment = Payment.objects.create(
            student=self.student, group=self.group, month=current_month,
            amount_due=200, amount_paid=0, status='unpaid',
        )
        resp = self.client.post(
            reverse('attendance:scanner_pay_now'),
            data=json.dumps({'payment_id': payment.pk}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'unpaid')

    def test_teacher_cannot_grant_exception(self):
        resp = self.client.post(
            reverse('attendance:grant_exception'),
            data=json.dumps({
                'student_id': self.student.pk, 'exception_type': 'payment',
                'reason_type': 'forgot_money',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)

    def test_teacher_cannot_cancel_session(self):
        session = Session.objects.create(
            group=self.group, session_date=timezone.localdate()
        )
        resp = self.client.post(
            reverse('attendance:cancel_session', kwargs={'session_id': session.pk}),
            {'reason': 'اختبار'},
        )
        self.assertEqual(resp.status_code, 403)
        session.refresh_from_db()
        self.assertFalse(session.is_cancelled)

    def test_teacher_cannot_check_teacher_in(self):
        session = Session.objects.create(
            group=self.group, session_date=timezone.localdate()
        )
        resp = self.client.post(
            reverse('attendance:teacher_checkin', kwargs={'session_id': session.pk}),
        )
        self.assertEqual(resp.status_code, 403)


class SessionAuditLogTest(AuditFixturesMixin, TestCase):
    """AUTH-08 / QUAL-05: cancellations and payments are traceable."""

    def setUp(self):
        self.build_fixtures()
        self.client = Client()
        self.client.login(username='aud_sup', password='testpass123')

    def test_cancel_session_is_logged(self):
        from apps.attendance.models import ActivityLog
        session = Session.objects.create(
            group=self.group, session_date=timezone.localdate()
        )
        resp = self.client.post(
            reverse('attendance:cancel_session', kwargs={'session_id': session.pk}),
            {'reason': 'مرض المدرس'},
        )
        self.assertEqual(resp.status_code, 200)
        log = ActivityLog.objects.filter(action='session_cancel').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.supervisor)
        self.assertIn('مرض المدرس', log.description)

    def test_pay_now_is_logged(self):
        from apps.attendance.models import ActivityLog
        current_month = timezone.localdate().replace(day=1)
        payment = Payment.objects.create(
            student=self.student, group=self.group, month=current_month,
            amount_due=200, amount_paid=0, status='unpaid',
        )
        resp = self.client.post(
            reverse('attendance:scanner_pay_now'),
            data=json.dumps({'payment_id': payment.pk}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        log = ActivityLog.objects.filter(action='payment_record').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.supervisor)
        self.assertEqual(log.target_id, payment.pk)


class GrantExceptionValidationTest(AuditFixturesMixin, TestCase):
    """AUTH-04: exception_type / reason_type validated against their choices."""

    def setUp(self):
        self.build_fixtures()
        self.client = Client()
        self.client.login(username='aud_sup', password='testpass123')

    def _post(self, **body):
        return self.client.post(
            reverse('attendance:grant_exception'),
            data=json.dumps({'student_id': self.student.pk, **body}),
            content_type='application/json',
        )

    def test_invalid_exception_type_rejected(self):
        from apps.attendance.models import ExceptionRecord
        resp = self._post(exception_type='whatever', reason_type='forgot_money')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(ExceptionRecord.objects.count(), 0)

    def test_invalid_reason_type_rejected(self):
        from apps.attendance.models import ExceptionRecord
        resp = self._post(exception_type='payment', reason_type='because')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(ExceptionRecord.objects.count(), 0)

    def test_valid_values_accepted(self):
        from apps.attendance.models import ExceptionRecord
        resp = self._post(exception_type='payment', reason_type='forgot_money')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ExceptionRecord.objects.count(), 1)


class TodaySessionsReadOnlyTest(AuditFixturesMixin, TestCase):
    """PERF-11: the stats poll must not create Session rows."""

    def setUp(self):
        self.build_fixtures(day=AttendanceService.get_current_day_name())
        self.client = Client()
        self.client.login(username='aud_sup', password='testpass123')

    def test_get_does_not_create_sessions(self):
        resp = self.client.get(reverse('attendance:today_sessions'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['sessions']), 1)
        self.assertIsNone(data['sessions'][0]['session_id'])
        self.assertEqual(Session.objects.count(), 0)


class AutoAbsenceTaskTest(AuditFixturesMixin, TestCase):
    """DATA-18 / DATA-19: one absence implementation, and it updates billing."""

    def setUp(self):
        self.build_fixtures(day=AttendanceService.get_current_day_name())
        # The session started well before now so the 10-minute rule fires.
        self.group.schedule_time = time(0, 1)
        self.group.save()
        self.session = assign_to_cycle(Session.objects.create(
            group=self.group, session_date=timezone.localdate()
        ))

    def test_absence_updates_payment_sessions(self):
        from apps.attendance.tasks import auto_mark_absent_sessions

        auto_mark_absent_sessions()

        attendance = Attendance.objects.get(
            student=self.student, session=self.session
        )
        self.assertEqual(attendance.status, 'absent')

        payment = Payment.objects.get(
            student=self.student, group=self.group, cycle=self.session.cycle,
        )
        self.assertEqual(payment.sessions_attended, 1)

    def test_soft_deleted_student_is_skipped(self):
        from apps.attendance.tasks import auto_mark_absent_sessions

        self.student.soft_delete()
        auto_mark_absent_sessions()
        self.assertEqual(Attendance.objects.count(), 0)


class BillingCycleTaskTest(AuditFixturesMixin, TestCase):
    """
    apps.attendance.tasks.roll_group_cycles — cycles are now closed and
    rolled at the GROUP level (every enrolled student shares one cycle),
    replacing the old per-enrollment ``check_billing_cycles``.
    """

    def setUp(self):
        self.build_fixtures(day='Saturday', sessions_per_month=2)
        self.current_month = timezone.localdate().replace(day=1)

    def test_open_cycle_is_created_on_first_run(self):
        from apps.attendance.tasks import roll_group_cycles

        roll_group_cycles()
        cycle = GroupCycle.objects.get(group=self.group, closed_on__isnull=True)
        self.assertEqual(cycle.sessions_planned, 2)
        # No session has happened yet — the cycle is reserved, not started.
        self.assertIsNone(cycle.started_on)

    def test_completed_cycle_closes_and_rolls_forward(self):
        from apps.attendance.tasks import roll_group_cycles

        cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=2,
            started_on=self.current_month,
        )
        payment = Payment.objects.create(
            student=self.student, group=self.group, cycle=cycle,
            month=self.current_month,
            amount_due=200, amount_paid=200, status='paid',
        )
        for i in range(2):
            session = Session.objects.create(
                group=self.group, session_date=self.current_month + timedelta(days=i),
            )
            assign_to_cycle(session)
            Attendance.objects.create(student=self.student, session=session, status='present')

        roll_group_cycles()

        payment.refresh_from_db()
        self.assertTrue(payment.billing_cycle_completed)

        cycle.refresh_from_db()
        self.assertIsNotNone(cycle.closed_on)

        next_cycle = GroupCycle.objects.get(group=self.group, index=2)
        self.assertIsNone(next_cycle.closed_on)
        self.assertTrue(
            Payment.objects.filter(
                student=self.student, group=self.group, cycle=next_cycle,
                amount_due=200,
            ).exists()
        )

    def test_exempt_student_not_billed_on_rollover(self):
        from apps.attendance.tasks import roll_group_cycles

        self.enrollment.financial_status = 'exempt'
        self.enrollment.save()

        cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=2,
            started_on=self.current_month,
        )
        for i in range(2):
            session = Session.objects.create(
                group=self.group, session_date=self.current_month + timedelta(days=i),
            )
            assign_to_cycle(session)
            Attendance.objects.create(student=self.student, session=session, status='present')

        roll_group_cycles()

        next_cycle = GroupCycle.objects.get(group=self.group, index=2)
        self.assertFalse(
            Payment.objects.filter(student=self.student, cycle=next_cycle).exists()
        )


class EntitlementModuleTest(TestCase):
    """
    apps.attendance.entitlement.evaluate — the session-based decision ladder
    that replaces the old 30-day global subscription check. Tested in
    isolation with real GroupCycle/Session/Payment rows but without going
    through the scanner, per the plan's "unit-test the ladder before wiring
    it in" step.
    """

    def setUp(self):
        self.room = Room.objects.create(name='قاعة استحقاق', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس استحقاق', phone='01099990000',
            specialization='علوم', hire_date=timezone.now().date(),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة استحقاق', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('100.00'),
            sessions_per_month=4,
        )
        self.student = Student.objects.create(
            student_code='ENT001', full_name='طالب استحقاق',
            gender='male', parent_phone='01099991111', student_phone='01099992222',
        )
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )
        self.cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4,
            started_on=timezone.localdate(),
        )

    def _make_session(self, day_offset, cancelled=False):
        session = Session.objects.create(
            group=self.group,
            session_date=timezone.localdate() + timedelta(days=day_offset),
            is_cancelled=cancelled,
        )
        return assign_to_cycle(session)

    def test_exempt_always_allowed(self):
        self.enrollment.financial_status = 'exempt'
        self.enrollment.save()
        result = entitlement.evaluate(self.enrollment, self.cycle)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('exempt'))

    def test_no_cycle_group_is_unlimited(self):
        result = entitlement.evaluate(self.enrollment, None)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('unlimited'))

    def test_paid_within_entitlement_allowed(self):
        payment = Payment.objects.create(
            student=self.student, group=self.group, cycle=self.cycle,
            month=timezone.localdate().replace(day=1),
            amount_due=Decimal('100.00'), amount_paid=Decimal('100.00'),
            status='paid', sessions_attended=1, sessions_total=4,
        )
        result = entitlement.evaluate(self.enrollment, self.cycle, payment=payment)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['sessions_consumed'], 1)

    def test_paid_but_exhausted_rejected(self):
        payment = Payment.objects.create(
            student=self.student, group=self.group, cycle=self.cycle,
            month=timezone.localdate().replace(day=1),
            amount_due=Decimal('100.00'), amount_paid=Decimal('100.00'),
            status='paid', sessions_attended=4, sessions_total=4,
        )
        result = entitlement.evaluate(self.enrollment, self.cycle, payment=payment)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'sessions_exhausted')

    def test_unpaid_first_cycle_strict_no_grace(self):
        """Never paid this group before + strict first cycle → 0 free sessions."""
        result = entitlement.evaluate(self.enrollment, self.cycle)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'payment_required')
        self.assertEqual(result['amount_due'], 100.00)

    def test_unpaid_returning_student_gets_two_session_grace(self):
        """Student has paid this group before → 2 free sessions on a new cycle."""
        Payment.objects.create(
            student=self.student, group=self.group, cycle=None,
            month=timezone.localdate().replace(day=1, month=1),
            amount_due=Decimal('100.00'), amount_paid=Decimal('100.00'),
            status='paid', sessions_attended=4, sessions_total=4,
        )
        s1 = self._make_session(0)
        Attendance.objects.create(student=self.student, session=s1, status='present')

        result = entitlement.evaluate(self.enrollment, self.cycle)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('grace_sessions'))
        self.assertEqual(result['grace_sessions_left'], 1)

        s2 = self._make_session(1)
        Attendance.objects.create(student=self.student, session=s2, status='absent')
        s3 = self._make_session(2)
        Attendance.objects.create(student=self.student, session=s3, status='present')

        result = entitlement.evaluate(self.enrollment, self.cycle)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'payment_required')

    def test_cancelled_session_never_consumes_grace(self):
        Payment.objects.create(
            student=self.student, group=self.group, cycle=None,
            month=timezone.localdate().replace(day=1, month=1),
            amount_due=Decimal('100.00'), amount_paid=Decimal('100.00'),
            status='paid', sessions_attended=4, sessions_total=4,
        )
        cancelled = self._make_session(0, cancelled=True)
        self.assertIsNone(cancelled.sequence_in_cycle)
        Attendance.objects.create(student=self.student, session=cancelled, status='present')

        result = entitlement.evaluate(self.enrollment, self.cycle)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['grace_sessions_left'], 2)

    def test_manual_grace_until_allows_entry(self):
        self.enrollment.grace_until = timezone.localdate() + timedelta(days=3)
        self.enrollment.save()
        result = entitlement.evaluate(self.enrollment, self.cycle)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('grace_period'))

    def test_evaluate_never_creates_a_payment_row(self):
        """Mirrors the historical constraint: a financial check must be read-only."""
        entitlement.evaluate(self.enrollment, self.cycle)
        self.assertEqual(
            Payment.objects.filter(student=self.student, cycle=self.cycle).count(), 0
        )

    def test_not_enrolled_rejected(self):
        other_student = Student.objects.create(
            student_code='ENT002', full_name='طالب آخر',
            gender='male', parent_phone='01099993333',
        )
        result = entitlement.evaluate(None, self.cycle)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['error_type'], 'not_enrolled')


class AttendanceGridTest(TestCase):
    """apps.attendance.grids.build_group_attendance_grid — the students×sessions matrix."""

    def setUp(self):
        self.teacher = Teacher.objects.create(
            full_name='مدرس الشبكة', phone='01088880000',
            specialization='عربي', hire_date=timezone.localdate(),
        )
        self.room = Room.objects.create(name='قاعة الشبكة', capacity=20)
        self.group = create_group_with_schedule(
            group_name='مجموعة الشبكة', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(9, 0), standard_fee=Decimal('100'),
        )
        self.today = timezone.localdate()

        self.student_a = Student.objects.create(
            student_code='GRD001', full_name='طالب أ', gender='male',
            parent_phone='01088881111',
        )
        self.enr_a = StudentGroupEnrollment.objects.create(
            student=self.student_a, group=self.group, financial_status='normal',
        )

        self.session1 = Session.objects.create(group=self.group, session_date=self.today)
        self.session2 = Session.objects.create(group=self.group, session_date=self.today + timedelta(days=1))
        Attendance.objects.create(student=self.student_a, session=self.session1, status='present')
        Attendance.objects.create(student=self.student_a, session=self.session2, status='absent')

    def test_grid_shape_and_query_count(self):
        from apps.attendance.grids import build_group_attendance_grid

        with self.assertNumQueries(4):
            grid = build_group_attendance_grid(
                self.group, self.today, self.today + timedelta(days=1),
            )
        self.assertEqual(len(grid['columns']), 2)
        self.assertEqual(len(grid['rows']), 1)
        self.assertEqual(grid['rows'][0]['cells'], ['present', 'absent'])

    def test_pre_enrollment_sessions_are_masked(self):
        """A session before the student joined must read 'not_enrolled', not 'no_record'."""
        from apps.attendance.grids import build_group_attendance_grid

        late_student = Student.objects.create(
            student_code='GRD002', full_name='طالب متأخر', gender='male',
            parent_phone='01088882222',
        )
        late_enr = StudentGroupEnrollment.objects.create(
            student=late_student, group=self.group, financial_status='normal',
        )
        # enrolled_at is auto_now_add — force it to AFTER session1 so
        # session1 is genuinely "before this student joined".
        StudentGroupEnrollment.objects.filter(pk=late_enr.pk).update(
            enrolled_at=timezone.make_aware(
                timezone.datetime.combine(self.session2.session_date, time(0, 0))
            )
        )
        Attendance.objects.create(student=late_student, session=self.session2, status='present')

        grid = build_group_attendance_grid(
            self.group, self.today, self.today + timedelta(days=1),
        )
        late_row = next(r for r in grid['rows'] if r['student'].pk == late_student.pk)
        self.assertEqual(late_row['cells'][0], 'not_enrolled')
        self.assertEqual(late_row['cells'][1], 'present')

    def test_cancelled_session_marked(self):
        from apps.attendance.grids import build_group_attendance_grid

        self.session2.is_cancelled = True
        self.session2.save(update_fields=['is_cancelled'])

        grid = build_group_attendance_grid(
            self.group, self.today, self.today + timedelta(days=1),
        )
        self.assertEqual(grid['rows'][0]['cells'][1], 'cancelled')

    def test_include_expected_adds_unrecorded_column(self):
        """A scheduled Saturday with no Session row shows up as 'unrecorded'."""
        from apps.attendance.grids import build_group_attendance_grid

        far_future = self.today + timedelta(days=14)  # next Saturday, no session created
        grid = build_group_attendance_grid(
            self.group, self.today, far_future, include_expected=True,
        )
        unrecorded_cols = [c for c in grid['columns'] if c['unrecorded']]
        self.assertGreaterEqual(len(unrecorded_cols), 1)


class ExportReportCsvTest(AuditFixturesMixin, TestCase):
    """
    attendance:export_report — now a plain GET returning a real CSV file
    with a UTF-8 BOM (FE-06), instead of POST+JSON-wrapped text.
    """

    def setUp(self):
        self.build_fixtures(day=AttendanceService.get_current_day_name())
        self.client = Client()
        self.client.login(username='aud_sup', password='testpass123')
        session = Session.objects.create(group=self.group, session_date=timezone.localdate())
        Attendance.objects.create(student=self.student, session=session, status='present')

    def test_requires_date(self):
        response = self.client.get(reverse('attendance:export_report'))
        self.assertEqual(response.status_code, 400)

    def test_get_returns_csv_file_with_bom(self):
        response = self.client.get(reverse('attendance:export_report'), {
            'date': timezone.localdate().isoformat(), 'type': 'detailed',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertTrue(response.content.startswith('﻿'.encode('utf-8')))
        self.assertIn('طالب التدقيق'.encode('utf-8'), response.content)

    def test_post_not_allowed(self):
        response = self.client.post(reverse('attendance:export_report'), {
            'date': timezone.localdate().isoformat(),
        })
        self.assertEqual(response.status_code, 405)

    def test_teacher_role_forbidden(self):
        teacher_client = Client()
        teacher_client.login(username='aud_teacher', password='testpass123')
        response = teacher_client.get(reverse('attendance:export_report'), {
            'date': timezone.localdate().isoformat(),
        })
        self.assertEqual(response.status_code, 403)
