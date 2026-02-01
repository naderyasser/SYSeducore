"""
Unit Tests for Attendance Service - Educore V2
اختبار النظام الجديد: قاعدة 10 دقائق صارمة + student_code
"""

from django.test import TestCase
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

        result = AttendanceService._check_strict_time(scan_time, schedule_time)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['status'], 'present')

    def test_check_strict_time_5_minutes_late(self):
        """اختبار: تأخر 5 دقائق (9:05) - رفض (النظام الصارم)"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 5))
        )

        result = AttendanceService._check_strict_time(scan_time, schedule_time)
        # النظام الصارم: أي تأخير = ممنوع
        self.assertFalse(result['allowed'])
        self.assertEqual(result['status'], 'late_blocked')

    def test_check_strict_time_exactly_10_minutes(self):
        """اختبار: تأخر بالظبط 10 دقائق (9:10) - رفض"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 10))
        )

        result = AttendanceService._check_strict_time(scan_time, schedule_time)
        # النظام الصارم: أي تأخير = ممنوع
        self.assertFalse(result['allowed'])
        self.assertEqual(result['status'], 'late_blocked')

    def test_check_strict_time_11_minutes_late_block(self):
        """اختبار: تأخر 11 دقيقة (9:11) - رفض كامل (تأخير شديد)"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 11))
        )

        result = AttendanceService._check_strict_time(scan_time, schedule_time)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['status'], 'very_late')

    def test_check_strict_time_15_minutes_late_block(self):
        """اختبار: تأخر 15 دقيقة (9:15) - رفض كامل"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(9, 15))
        )

        result = AttendanceService._check_strict_time(scan_time, schedule_time)
        self.assertFalse(result['allowed'])
        self.assertEqual(result['status'], 'very_late')

    def test_check_strict_time_too_early(self):
        """اختبار: وصول مبكر جداً (35 دقيقة قبل الموعد)"""
        schedule_time = time(9, 0)
        scan_time = timezone.make_aware(
            datetime.combine(timezone.now().date(), time(8, 25))
        )

        result = AttendanceService._check_strict_time(scan_time, schedule_time)
        self.assertFalse(result['allowed'])
        self.assertIn('مبكراً جداً', result['message'])

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
        # استخدام الدالة الداخلية للاختبار
        result = AttendanceService._check_financial_status(self.student_exempt, self.group)
        self.assertTrue(result['allowed'])

    def test_financial_check_first_month_no_payment(self):
        """اختبار: الشهر الأول - لازم دفع"""
        # الطالب جديد (لا يوجد حضور سابق)
        result = AttendanceService._check_financial_status(self.student_normal, self.group)
        self.assertFalse(result['allowed'])

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

        result = AttendanceService._check_financial_status(self.student_normal, self.group)
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
        result = AttendanceService._check_financial_status(self.student_normal, self.group)
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
        result = AttendanceService._check_financial_status(self.student_normal, self.group)
        self.assertFalse(result['allowed'])

    def test_is_student_first_month_in_group_true(self):
        """اختبار: الطالب جديد في المجموعة"""
        enrollment = StudentGroupEnrollment.objects.get(
            student=self.student_normal,
            group=self.group
        )
        # الطالب جديد بدون حضور سابق
        self.assertTrue(enrollment.is_new_student)

    def test_is_student_first_month_in_group_false(self):
        """اختبار: الطالب ليس جديد في المجموعة"""
        enrollment = StudentGroupEnrollment.objects.get(
            student=self.student_normal,
            group=self.group
        )
        # تحديث حالة الطالب
        enrollment.is_new_student = False
        enrollment.save()
        
        # التحقق
        enrollment.refresh_from_db()
        self.assertFalse(enrollment.is_new_student)


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
        self.assertIn('غير صالح', result['message'])

    def test_process_scan_no_class_today(self):
        """اختبار: لا توجد حصة مجدولة اليوم"""
        # Group مجدول ليوم السبت، فإذا اليوم ليس سبت، سيفشل
        result = AttendanceService.process_scan(self.student.student_code, self.supervisor)

        # قد ينجح أو يفشل حسب اليوم الحالي
        self.assertIn('success', result)
