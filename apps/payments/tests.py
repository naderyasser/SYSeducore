"""
Tests for Payment Service
"""

from datetime import time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from apps.teachers.models import Teacher, Group, Room
from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Session, Attendance
from apps.payments.models import Payment
from apps.payments.services import SettlementService


class SettlementServiceTest(TestCase):

    def setUp(self):
        """Set up test data"""
        # Create teacher
        self.teacher = Teacher.objects.create(
            full_name='Test Teacher',
            phone='01234567890',
            specialization='Math',
            hire_date=timezone.now().date(),
        )

        # Create room
        self.room = Room.objects.create(name='Test Room', capacity=30)

        # Create group
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(10, 0),
            standard_fee=Decimal('300.00'),
            center_percentage=Decimal('30.00'),
        )

        # Create students and enroll them
        self.student1 = Student.objects.create(
            student_code='SET001',
            full_name='Student 1',
            parent_phone='01234567891',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student1,
            group=self.group,
            financial_status='normal',
        )

        self.student2 = Student.objects.create(
            student_code='SET002',
            full_name='Student 2',
            parent_phone='01234567892',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student2,
            group=self.group,
            financial_status='normal',
        )

        # Create sessions and attendance
        for i in range(4):
            session = Session.objects.create(
                group=self.group,
                session_date=timezone.now().date() - timedelta(days=i * 7),
            )

            Attendance.objects.create(
                student=self.student1,
                session=session,
                status='present',
            )

            Attendance.objects.create(
                student=self.student2,
                session=session,
                status='present',
            )

        # Create payments
        Payment.objects.create(
            student=self.student1,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('300.00'),
            status='paid',
        )

        Payment.objects.create(
            student=self.student2,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('300.00'),
            status='paid',
        )

        self.service = SettlementService()

    def test_calculate_teacher_settlement(self):
        """Test teacher settlement calculation"""
        now = timezone.now().date()
        result = self.service.calculate_teacher_settlement(
            self.teacher.pk, now.year, now.month,
        )
        self.assertIn('total_revenue', result)
        self.assertIn('teacher_share', result)

    def test_calculate_group_revenue(self):
        """Test group revenue calculation"""
        now = timezone.now().date()
        result = self.service.calculate_group_revenue(
            self.group.pk, now.year, now.month,
        )
        self.assertIn('total_revenue', result)

    def test_calculate_settlement_with_different_center_percentage(self):
        """Test settlement with different center percentage"""
        self.group.center_percentage = Decimal('40.00')
        self.group.save()

        now = timezone.now().date()
        result = self.service.calculate_teacher_settlement(
            self.teacher.pk, now.year, now.month,
        )
        self.assertIn('teacher_share', result)

    def test_calculate_settlement_with_symbolic_students(self):
        """Test settlement with symbolic students"""
        symbolic_student = Student.objects.create(
            student_code='SET003',
            full_name='Symbolic Student',
            parent_phone='01234567893',
        )
        StudentGroupEnrollment.objects.create(
            student=symbolic_student,
            group=self.group,
            financial_status='symbolic',
            custom_fee=Decimal('100.00'),
        )

        session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date(),
        )

        Attendance.objects.create(
            student=symbolic_student,
            session=session,
            status='present',
        )

        now = timezone.now().date()
        result = self.service.calculate_teacher_settlement(
            self.teacher.pk, now.year, now.month,
        )
        self.assertIn('total_revenue', result)


class PaymentModelTest(TestCase):

    def setUp(self):
        """Set up test data"""
        self.room = Room.objects.create(name='Pay Room', capacity=30)
        self.teacher = Teacher.objects.create(
            full_name='Pay Teacher',
            phone='01234567800',
            specialization='Science',
            hire_date=timezone.now().date(),
        )
        self.group = Group.objects.create(
            group_name='Pay Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(14, 0),
            standard_fee=Decimal('300.00'),
            center_percentage=Decimal('30.00'),
        )

        self.student = Student.objects.create(
            student_code='PAY001',
            full_name='Test Student',
            parent_phone='01234567890',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal',
        )

        self.payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('0.00'),
            status='unpaid',
        )

    def test_payment_creation(self):
        """Test payment creation"""
        self.assertEqual(self.payment.amount_due, Decimal('300.00'))
        self.assertEqual(self.payment.status, 'unpaid')

    def test_payment_status_unpaid(self):
        """Test unpaid status"""
        self.assertEqual(self.payment.status, 'unpaid')

    def test_payment_status_partial(self):
        """Test partial payment status"""
        self.payment.amount_paid = Decimal('100.00')
        self.payment.status = 'partial'
        self.payment.save()
        self.assertEqual(self.payment.status, 'partial')

    def test_payment_status_paid(self):
        """Test paid status"""
        self.payment.amount_paid = Decimal('300.00')
        self.payment.status = 'paid'
        self.payment.save()
        self.assertEqual(self.payment.status, 'paid')

    def test_str_representation(self):
        """Test string representation"""
        s = str(self.payment)
        self.assertIsNotNone(s)
