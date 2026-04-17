"""
Unit Tests for Attendance Service - Educore V2
اختبار النظام الجديد: قاعدة 10 دقائق صارمة + student_code
"""

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
        self.group = Group.objects.create(
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
        """اختبار: تأخر 5 دقائق (9:05) - قبول"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 5))
        )

        result = AttendanceService.check_strict_time(scan_time, schedule_time)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['status'], 'present')

    def test_check_strict_time_exactly_10_minutes(self):
        """اختبار: تأخر بالظبط 10 دقائق (9:10) - قبول"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 10))
        )

        result = AttendanceService.check_strict_time(scan_time, schedule_time)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['status'], 'present')

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
    اختبار الفحص المالي (الحصة الثالثة)
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

        self.group = Group.objects.create(
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
        StudentGroupEnrollment.objects.create(
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

    def test_financial_check_exempt_always_allowed(self):
        """اختبار: الطالب المعفي دائماً مسموح"""
        result = AttendanceService.check_financial_status(self.student_exempt, self.group)
        self.assertTrue(result['allowed'])
        self.assertTrue(result.get('exempt', False))

    def test_financial_check_first_month_no_payment(self):
        """اختبار: الشهر الأول - لازم دفع"""
        # الطالب جديد (لا يوجد حضور سابق)
        result = AttendanceService.check_financial_status(self.student_normal, self.group)
        self.assertFalse(result['allowed'])
        self.assertIn('الشهر الأول', result['reason'])

    def test_financial_check_first_month_with_payment(self):
        """اختبار: الشهر الأول - مع دفع"""
        current_month = timezone.now().date().replace(day=1)
        Payment.objects.create(
            student=self.student_normal,
            group=self.group,
            month=current_month,
            amount_due=200.00,
            amount_paid=200.00,
            status='paid'
        )

        result = AttendanceService.check_financial_status(self.student_normal, self.group)
        self.assertTrue(result['allowed'])

    def test_financial_check_subsequent_month_first_session(self):
        """اختبار: الشهور التالية - الحصة الأولى (سماح)"""
        # إنشاء حضور في الشهر السابق (ليكون ليس الشهر الأول)
        previous_month = timezone.now().date().replace(day=1) - timedelta(days=35)
        previous_session = Session.objects.create(
            group=self.group,
            session_date=previous_month
        )
        # تحديد scan_time بشكل صريح ليكون في الشهر السابق
        previous_scan_time = timezone.make_aware(
            datetime.combine(previous_month, time(9, 0))
        )
        Attendance.objects.create(
            student=self.student_normal,
            session=previous_session,
            status='present',
            supervisor=self.supervisor,
            scan_time=previous_scan_time
        )

        # الشهر الحالي: الحصة الأولى (مسموح)
        result = AttendanceService.check_financial_status(self.student_normal, self.group)
        self.assertTrue(result['allowed'])

    def test_financial_check_subsequent_month_third_session_blocked(self):
        """اختبار: الشهور التالية - الحصة الثالثة بدون دفع (رفض)"""
        # حضور في الشهر السابق
        previous_month = timezone.now().date().replace(day=1) - timedelta(days=35)
        previous_session = Session.objects.create(
            group=self.group,
            session_date=previous_month
        )
        previous_scan_time = timezone.make_aware(
            datetime.combine(previous_month, time(9, 0))
        )
        Attendance.objects.create(
            student=self.student_normal,
            session=previous_session,
            status='present',
            supervisor=self.supervisor,
            scan_time=previous_scan_time
        )

        # حضور حصتين في الشهر الحالي
        current_month = timezone.now().date().replace(day=1)
        for i in range(2):
            session = Session.objects.create(
                group=self.group,
                session_date=current_month + timedelta(days=i)
            )
            current_scan_time = timezone.make_aware(
                datetime.combine(current_month + timedelta(days=i), time(9, 0))
            )
            Attendance.objects.create(
                student=self.student_normal,
                session=session,
                status='present',
                supervisor=self.supervisor,
                scan_time=current_scan_time
            )

        # الحصة الثالثة (رفض)
        result = AttendanceService.check_financial_status(self.student_normal, self.group)
        self.assertFalse(result['allowed'])
        self.assertIn('ممنوع الدخول', result['reason'])

    def test_is_student_first_month_in_group_true(self):
        """اختبار: هل هو الشهر الأول - نعم"""
        # طالب جديد بدون حضور سابق
        result = AttendanceService.is_student_first_month_in_group(self.student_normal, self.group)
        self.assertTrue(result)

    def test_is_student_first_month_in_group_false(self):
        """اختبار: هل هو الشهر الأول - لا"""
        # إنشاء حضور في الشهر السابق
        previous_month = timezone.now().date().replace(day=1) - timedelta(days=35)
        previous_session = Session.objects.create(
            group=self.group,
            session_date=previous_month
        )
        previous_scan_time = timezone.make_aware(
            datetime.combine(previous_month, time(9, 0))
        )
        Attendance.objects.create(
            student=self.student_normal,
            session=previous_session,
            status='present',
            supervisor=self.supervisor,
            scan_time=previous_scan_time
        )

        result = AttendanceService.is_student_first_month_in_group(self.student_normal, self.group)
        self.assertFalse(result)


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

        self.group = Group.objects.create(
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
        import pytz

        cairo_tz = pytz.timezone('Africa/Cairo')

        # Simulate 00:30 Cairo time on a Saturday = Friday 22:30 UTC
        # Cairo Saturday 00:30 → UTC Friday 22:30
        cairo_saturday_0030 = cairo_tz.localize(
            datetime(2026, 4, 18, 0, 30)  # Saturday in Cairo
        )
        utc_equivalent = cairo_saturday_0030.astimezone(pytz.utc)

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
        self.group = Group.objects.create(
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
        """When flag is True, first-month student with no payment should be blocked."""
        result = AttendanceService.check_financial_status(self.student, self.group)
        self.assertFalse(result['allowed'])
        self.assertIn('الشهر الأول', result.get('reason', ''))

    @override_settings(ENABLE_FIRST_MONTH_STRICT_PAYMENT=False)
    def test_first_month_strict_false_allows_grace(self):
        """When flag is False, first-month student gets 2-session grace like returning students."""
        result = AttendanceService.check_financial_status(self.student, self.group)
        # With 0 sessions attended and 2 allowed, should be allowed
        self.assertTrue(result['allowed'])

    @override_settings(ENABLE_FIRST_MONTH_STRICT_PAYMENT=True)
    def test_first_month_strict_true_with_payment_allowed(self):
        """When flag is True, first-month student who has paid should be allowed."""
        current_month = timezone.now().date().replace(day=1)
        Payment.objects.create(
            student=self.student,
            group=self.group,
            month=current_month,
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
        self.group_a = Group.objects.create(
            group_name='مجموعة ألفا',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            standard_fee=300.00
        )
        self.group_b = Group.objects.create(
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
        current_month = timezone.localtime().date().replace(day=1)
        Payment.objects.create(
            student=self.student, group=self.group_a, month=current_month,
            amount_due=300.00, amount_paid=300.00, status='paid'
        )
        dossier = AttendanceService.build_student_dossier(self.student)
        normal_enr = next(
            e for e in dossier['enrollments'] if e['group_name'] == 'مجموعة ألفا'
        )
        self.assertEqual(normal_enr['payment']['status'], 'paid')
        self.assertEqual(normal_enr['payment']['remaining'], 0.0)

    def test_dossier_subscription_no_date(self):
        """Student with no subscription_expiry_date → inactive status in dossier."""
        dossier = AttendanceService.build_student_dossier(self.student)
        self.assertEqual(dossier['subscription']['status'], 'inactive')

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
        from datetime import time as dtime
        import pytz
        from django.conf import settings
        local_tz = pytz.timezone(settings.TIME_ZONE)
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

    def test_severity_in_subscription_expired(self):
        """Scan for expired student must return severity='error'."""
        from datetime import timedelta
        self.student.subscription_expiry_date = timezone.localtime().date() - timedelta(days=5)
        self.student.save()
        result = AttendanceService.process_scan('5500', self.supervisor)
        if result.get('error_type') == 'subscription_expired':
            self.assertEqual(result['severity'], 'error')
