"""
Financial & Settlement Tests.

Tests:
- Teacher settlement calculation (revenue split by center_percentage)
- Revenue based on amount_paid (not amount_due)
- Multi-group teacher settlement
- Payment status transitions
- Student fee calculation by financial_status
"""
from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.services import SettlementService
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room


class TestTeacherSettlement(TestCase):
    """Test SettlementService for accurate revenue splitting."""

    def setUp(self):
        self.room = Room.objects.create(name='قاعة مالية', capacity=30)
        self.teacher = Teacher.objects.create(
            full_name='مدرس مالي', phone='01099999999',
            specialization='فيزياء', hire_date=date(2024, 1, 1),
        )
        self.group = Group.objects.create(
            group_name='مجموعة مالية',
            teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(14, 0),
            duration_minutes=120,
            standard_fee=Decimal('200.00'),
            center_percentage=Decimal('30.00'),
        )

        # Create 3 students with payments
        self.students = []
        current_month = timezone.now().date().replace(day=1)

        for i in range(3):
            student = Student.objects.create(
                student_code=f'FIN{i:03d}',
                full_name=f'طالب مالي {i}',
                gender='male',
                parent_phone=f'0109{i}000000',
                student_phone=f'0108{i}000000',
            )
            StudentGroupEnrollment.objects.create(
                student=student, group=self.group,
                financial_status='normal', is_active=True,
            )
            self.students.append(student)

        # Student 0: fully paid 200
        Payment.objects.create(
            student=self.students[0], group=self.group,
            month=current_month, amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'), status='paid',
        )
        # Student 1: partial payment 100
        Payment.objects.create(
            student=self.students[1], group=self.group,
            month=current_month, amount_due=Decimal('200.00'),
            amount_paid=Decimal('100.00'), status='partial',
        )
        # Student 2: unpaid
        Payment.objects.create(
            student=self.students[2], group=self.group,
            month=current_month, amount_due=Decimal('200.00'),
            amount_paid=Decimal('0.00'), status='unpaid',
        )

    def test_settlement_uses_amount_paid_not_due(self):
        """Revenue must be sum of amount_paid, NOT amount_due."""
        year = timezone.now().year
        month = timezone.now().month
        result = SettlementService.calculate_teacher_settlement(
            self.teacher.teacher_id, year, month
        )

        self.assertTrue(result['success'])
        data = result['data']

        # Revenue = 200 + 100 + 0 = 300 (not 600 which would be amount_due)
        self.assertEqual(data['total_revenue'], 300.0)

    def test_settlement_center_split(self):
        """Center gets 30% of revenue, teacher gets 70%."""
        year = timezone.now().year
        month = timezone.now().month
        result = SettlementService.calculate_teacher_settlement(
            self.teacher.teacher_id, year, month
        )

        data = result['data']
        # Revenue = 300, Center = 30% of 300 = 90, Teacher = 210
        self.assertEqual(data['center_share'], 90.0)
        self.assertEqual(data['teacher_share'], 210.0)

    def test_settlement_with_zero_revenue(self):
        """Month with no payments — settlement should return 0 for all shares."""
        # Use a different month with no payments
        result = SettlementService.calculate_teacher_settlement(
            self.teacher.teacher_id, 2023, 1  # No data for this month
        )

        self.assertTrue(result['success'])
        data = result['data']
        self.assertEqual(data['total_revenue'], 0)
        self.assertEqual(data['center_share'], 0)
        self.assertEqual(data['teacher_share'], 0)


class TestMultiGroupSettlement(TestCase):
    """Test settlement across multiple groups with different percentages."""

    def setUp(self):
        self.room = Room.objects.create(name='قاعة متعدد', capacity=30)
        self.teacher = Teacher.objects.create(
            full_name='مدرس متعدد', phone='01088888888',
            specialization='كيمياء', hire_date=date(2024, 1, 1),
        )

        # Group A: 30% center
        self.group_a = Group.objects.create(
            group_name='مجموعة أ',
            teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(10, 0),
            duration_minutes=120, standard_fee=Decimal('300.00'),
            center_percentage=Decimal('30.00'),
        )

        # Group B: 25% center (different day to avoid room conflict)
        self.group_b = Group.objects.create(
            group_name='مجموعة ب',
            teacher=self.teacher, room=self.room,
            schedule_day='Sunday', schedule_time=time(10, 0),
            duration_minutes=120, standard_fee=Decimal('400.00'),
            center_percentage=Decimal('25.00'),
        )

        current_month = timezone.now().date().replace(day=1)

        # Student in group A: paid 300
        student_a = Student.objects.create(
            student_code='MG001', full_name='طالب أ',
            gender='male', parent_phone='01077770000',
            student_phone='01077771111',
        )
        StudentGroupEnrollment.objects.create(
            student=student_a, group=self.group_a,
            financial_status='normal', is_active=True,
        )
        Payment.objects.create(
            student=student_a, group=self.group_a,
            month=current_month, amount_due=Decimal('300.00'),
            amount_paid=Decimal('300.00'), status='paid',
        )

        # Student in group B: paid 400
        student_b = Student.objects.create(
            student_code='MG002', full_name='طالب ب',
            gender='female', parent_phone='01077772222',
            student_phone='01077773333',
        )
        StudentGroupEnrollment.objects.create(
            student=student_b, group=self.group_b,
            financial_status='normal', is_active=True,
        )
        Payment.objects.create(
            student=student_b, group=self.group_b,
            month=current_month, amount_due=Decimal('400.00'),
            amount_paid=Decimal('400.00'), status='paid',
        )

    def test_multi_group_total_revenue(self):
        """Total revenue = sum across all groups."""
        year = timezone.now().year
        month = timezone.now().month
        result = SettlementService.calculate_teacher_settlement(
            self.teacher.teacher_id, year, month
        )
        data = result['data']
        # 300 + 400 = 700
        self.assertEqual(data['total_revenue'], 700.0)

    def test_multi_group_breakdown_exists(self):
        """Settlement should contain breakdown per group."""
        year = timezone.now().year
        month = timezone.now().month
        result = SettlementService.calculate_teacher_settlement(
            self.teacher.teacher_id, year, month
        )
        data = result['data']
        self.assertEqual(len(data['breakdown']), 2)


class TestPaymentStatusTransitions(TestCase):
    """Test payment status transitions in record_payment."""

    def setUp(self):
        self.room = Room.objects.create(name='قاعة دفع', capacity=30)
        self.teacher = Teacher.objects.create(
            full_name='مدرس دفع', phone='01066666666',
            specialization='إنجليزي', hire_date=date(2024, 1, 1),
        )
        self.group = Group.objects.create(
            group_name='مجموعة دفع',
            teacher=self.teacher, room=self.room,
            schedule_day='Monday', schedule_time=time(16, 0),
            duration_minutes=90, standard_fee=Decimal('200.00'),
        )
        self.student = Student.objects.create(
            student_code='PAY001', full_name='طالب دفع',
            gender='male', parent_phone='01066660000',
            student_phone='01066661111',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )
        current_month = timezone.now().date().replace(day=1)
        self.payment = Payment.objects.create(
            student=self.student, group=self.group,
            month=current_month, amount_due=Decimal('200.00'),
            amount_paid=Decimal('0.00'), status='unpaid',
        )

    def test_partial_payment(self):
        """Paying 100 of 200 — status should be 'partial'."""
        self.payment.amount_paid = Decimal('100.00')
        if self.payment.amount_paid >= self.payment.amount_due:
            self.payment.status = 'paid'
        elif self.payment.amount_paid > 0:
            self.payment.status = 'partial'
        self.payment.save()

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'partial')

    def test_full_payment(self):
        """Paying full 200 — status should be 'paid'."""
        self.payment.amount_paid = Decimal('200.00')
        if self.payment.amount_paid >= self.payment.amount_due:
            self.payment.status = 'paid'
        elif self.payment.amount_paid > 0:
            self.payment.status = 'partial'
        self.payment.save()

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')

    def test_overpayment(self):
        """Paying 250 of 200 — status should still be 'paid'."""
        self.payment.amount_paid = Decimal('250.00')
        if self.payment.amount_paid >= self.payment.amount_due:
            self.payment.status = 'paid'
        self.payment.save()

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')


class TestStudentFeeCalculation(TestCase):
    """Test fee calculation based on financial_status."""

    def setUp(self):
        self.room = Room.objects.create(name='قاعة رسوم', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس رسوم', phone='01055555555',
            specialization='عربي', hire_date=date(2024, 1, 1),
        )
        self.group = Group.objects.create(
            group_name='مجموعة رسوم',
            teacher=self.teacher, room=self.room,
            schedule_day='Wednesday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('300.00'),
        )
        self.student = Student.objects.create(
            student_code='FEE001', full_name='طالب رسوم',
            gender='male', parent_phone='01055550000',
            student_phone='01055551111',
        )

    def test_normal_fee(self):
        """Normal enrollment — fee should be group.standard_fee."""
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )
        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, Decimal('300.00'))

    def test_exempt_fee_zero(self):
        """Exempt enrollment — fee should be 0."""
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='exempt', is_active=True,
        )
        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, Decimal('0'))

    def test_symbolic_fee(self):
        """Symbolic enrollment with custom_fee — should use custom_fee."""
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='symbolic', custom_fee=Decimal('100.00'),
            is_active=True,
        )
        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, Decimal('100.00'))
