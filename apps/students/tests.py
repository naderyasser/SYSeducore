"""
Unit Tests for Student App - Educore V2
اختبارات شاملة للنظام الجديد
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from .models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room


class StudentModelTest(TestCase):
    """
    Unit Tests للـ Student Model
    اختبار التغيير من barcode إلى student_code
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.student_data = {
            'student_code': '1001',
            'full_name': 'أحمد محمد',
            'parent_phone': '+201234567890'
        }

    def test_create_student_with_student_code(self):
        """اختبار: إنشاء طالب بـ student_code"""
        student = Student.objects.create(**self.student_data)

        self.assertEqual(student.student_code, '1001')
        self.assertEqual(student.full_name, 'أحمد محمد')
        self.assertTrue(student.is_active)

    def test_student_code_is_unique(self):
        """اختبار: student_code يجب أن يكون فريداً"""
        Student.objects.create(**self.student_data)

        # محاولة إنشاء طالب آخر بنفس الكود
        with self.assertRaises(IntegrityError):
            Student.objects.create(**self.student_data)

    def test_student_code_max_length(self):
        """اختبار: student_code الحد الأقصى 10 أحرف"""
        student = Student.objects.create(
            student_code='1234567890',  # 10 أحرف - OK
            full_name='Test Student',
            parent_phone='+201234567890'
        )
        self.assertEqual(len(student.student_code), 10)

    def test_student_str_representation(self):
        """اختبار: __str__ يرجع الاسم الكامل"""
        student = Student.objects.create(**self.student_data)
        self.assertEqual(str(student), 'أحمد محمد')


class StudentGroupEnrollmentTest(TestCase):
    """
    Unit Tests لنموذج تسجيل الطالب في المجموعة
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        # إنشاء مدرس
        self.teacher = Teacher.objects.create(
            full_name='محمد علي',
            email='teacher@test.com',
            phone='+201234567890',
            specialization='رياضيات',
            hire_date='2020-01-01'
        )

        # إنشاء قاعة
        self.room = Room.objects.create(
            name='قاعة A',
            capacity=30
        )

        # إنشاء مجموعة
        self.group = Group.objects.create(
            group_name='مجموعة السبت',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        # إنشاء طالب
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='+201234567890'
        )

    def test_create_enrollment_normal_status(self):
        """اختبار: إنشاء تسجيل بحالة مالية عادية"""
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

        self.assertEqual(enrollment.financial_status, 'normal')
        self.assertIsNone(enrollment.custom_fee)
        self.assertTrue(enrollment.is_active)

    def test_create_enrollment_exempt_status(self):
        """اختبار: إنشاء تسجيل بحالة إعفاء كامل"""
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='exempt'
        )

        self.assertEqual(enrollment.financial_status, 'exempt')
        # الطالب المعفي: المصروفات = 0
        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, 0)

    def test_create_enrollment_symbolic_status(self):
        """اختبار: إنشاء تسجيل بحالة مبلغ رمزي"""
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='symbolic',
            custom_fee=50.00
        )

        self.assertEqual(enrollment.financial_status, 'symbolic')
        self.assertEqual(enrollment.custom_fee, 50.00)

        # المصروفات = المبلغ الرمزي
        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, 50.00)

    def test_unique_student_group_constraint(self):
        """اختبار: لا يمكن تسجيل طالب في نفس المجموعة مرتين"""
        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group
        )

        # محاولة تسجيل مرة ثانية
        with self.assertRaises(IntegrityError):
            StudentGroupEnrollment.objects.create(
                student=self.student,
                group=self.group
            )

    def test_get_monthly_fee_for_group_normal(self):
        """اختبار: حساب المصروفات الشهرية - حالة عادية"""
        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, 200.00)  # السعر القياسي
