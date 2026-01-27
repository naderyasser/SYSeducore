"""
Tests for Payment Service
"""

from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta, time
from decimal import Decimal
from apps.teachers.models import Teacher, Group, Room
from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Session, Attendance
from apps.payments.models import Payment


class PaymentModelTest(TestCase):
    """Test Payment model"""

    def setUp(self):
        """Set up test data"""
        # Create teacher
        self.teacher = Teacher.objects.create(
            full_name='Test Teacher',
            phone='01234567890',
            email='teacher@test.com',
            specialization='Math',
            hire_date=timezone.now().date()
        )

        # Create room
        self.room = Room.objects.create(
            name='Test Room',
            capacity=30
        )

        # Create group
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(10, 0),
            standard_fee=Decimal('300.00'),
            center_percentage=Decimal('30.00')
        )

        # Create student
        self.student = Student.objects.create(
            student_code='PAY001',
            full_name='Test Student',
            parent_phone='01234567890'
        )

        # Enroll student in group
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

        # Create payment
        self.payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('0.00'),
            status='unpaid'
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

    def test_payment_str_representation(self):
        """Test string representation"""
        expected = f"{self.student.full_name} - {self.group.group_name} - {self.payment.month.strftime('%Y-%m')}"
        self.assertEqual(str(self.payment), expected)


class PaymentCalculationTest(TestCase):
    """Test payment calculations"""

    def setUp(self):
        """Set up test data"""
        # Create teacher
        self.teacher = Teacher.objects.create(
            full_name='Test Teacher',
            phone='01234567890',
            email='teacher@test.com',
            specialization='Math',
            hire_date=timezone.now().date()
        )

        # Create room
        self.room = Room.objects.create(
            name='Test Room',
            capacity=30
        )

        # Create group with standard fee
        self.group = Group.objects.create(
            group_name='Math Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(10, 0),
            standard_fee=Decimal('400.00'),
            center_percentage=Decimal('25.00')
        )

        # Create students with different financial statuses
        self.normal_student = Student.objects.create(
            student_code='CALC001',
            full_name='Normal Student',
            parent_phone='01234567891'
        )
        StudentGroupEnrollment.objects.create(
            student=self.normal_student,
            group=self.group,
            financial_status='normal'
        )

        self.symbolic_student = Student.objects.create(
            student_code='CALC002',
            full_name='Symbolic Student',
            parent_phone='01234567892'
        )
        StudentGroupEnrollment.objects.create(
            student=self.symbolic_student,
            group=self.group,
            financial_status='symbolic',
            custom_fee=Decimal('100.00')
        )

        self.exempt_student = Student.objects.create(
            student_code='CALC003',
            full_name='Exempt Student',
            parent_phone='01234567893'
        )
        StudentGroupEnrollment.objects.create(
            student=self.exempt_student,
            group=self.group,
            financial_status='exempt'
        )

    def test_normal_student_fee(self):
        """Test normal student pays standard fee"""
        fee = self.normal_student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, Decimal('400.00'))

    def test_symbolic_student_fee(self):
        """Test symbolic student pays custom fee"""
        fee = self.symbolic_student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, Decimal('100.00'))

    def test_exempt_student_fee(self):
        """Test exempt student pays nothing"""
        fee = self.exempt_student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, 0)


class PaymentStatusTest(TestCase):
    """Test payment status transitions"""

    def setUp(self):
        """Set up test data"""
        self.teacher = Teacher.objects.create(
            full_name='Test Teacher',
            phone='01234567890',
            email='teacher@test.com',
            specialization='Math',
            hire_date=timezone.now().date()
        )

        self.room = Room.objects.create(
            name='Test Room',
            capacity=30
        )

        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(10, 0),
            standard_fee=Decimal('300.00'),
            center_percentage=Decimal('30.00')
        )

        self.student = Student.objects.create(
            student_code='STATUS001',
            full_name='Status Test Student',
            parent_phone='01234567890'
        )

        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

    def test_create_unpaid_payment(self):
        """Test creating unpaid payment"""
        payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('0.00'),
            status='unpaid'
        )
        self.assertEqual(payment.status, 'unpaid')

    def test_partial_payment(self):
        """Test partial payment"""
        payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('150.00'),
            status='partial'
        )
        self.assertEqual(payment.status, 'partial')
        self.assertEqual(payment.amount_due - payment.amount_paid, Decimal('150.00'))

    def test_full_payment(self):
        """Test full payment"""
        payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('300.00'),
            status='paid'
        )
        self.assertEqual(payment.status, 'paid')

    def test_overpayment(self):
        """Test overpayment (advance)"""
        payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('400.00'),
            status='paid'
        )
        self.assertEqual(payment.status, 'paid')
        # Overpayment is recorded
        self.assertGreater(payment.amount_paid, payment.amount_due)
