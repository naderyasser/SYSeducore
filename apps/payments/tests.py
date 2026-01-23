"""
Tests for Payment Service
"""

from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta
from apps.teachers.models import Teacher, Group
from apps.students.models import Student
from apps.attendance.models import Session, Attendance
from apps.payments.models import Payment
from apps.payments.services import SettlementService


class SettlementServiceTest(TestCase):
    
    def setUp(self):
        """Set up test data"""
        # Create teacher
        self.teacher = Teacher.objects.create(
            name='Test Teacher',
            phone='01234567890'
        )
        
        # Create group
        self.group = Group.objects.create(
            name='Test Group',
            subject='Math',
            grade='Grade 1',
            teacher=self.teacher,
            schedule_day='saturday',
            start_time='10:00',
            end_time='12:00',
            center_percentage=30
        )
        
        # Create students
        self.student1 = Student.objects.create(
            name='Student 1',
            phone='01234567891',
            group=self.group,
            financial_status='normal',
            barcode='1234567890'
        )
        
        self.student2 = Student.objects.create(
            name='Student 2',
            phone='01234567892',
            group=self.group,
            financial_status='normal',
            barcode='1234567891'
        )
        
        # Create sessions and attendance
        for i in range(4):
            session = Session.objects.create(
                group=self.group,
                session_date=timezone.now().date() - timedelta(days=i*7)
            )
            
            # Create attendance for both students
            Attendance.objects.create(
                student=self.student1,
                session=session,
                status='present'
            )
            
            Attendance.objects.create(
                student=self.student2,
                session=session,
                status='present'
            )
        
        # Create payments
        Payment.objects.create(
            student=self.student1,
            month='2024-01',
            amount_due=300,
            amount_paid=300,
            status='paid'
        )
        
        Payment.objects.create(
            student=self.student2,
            month='2024-01',
            amount_due=300,
            amount_paid=300,
            status='paid'
        )
        
        self.service = SettlementService()
    
    def test_calculate_teacher_settlement(self):
        """Test teacher settlement calculation"""
        # 4 sessions * 2 students * 300 EGP = 2400 EGP total
        # Teacher share = 2400 - (2400 * 0.30) = 1680 EGP
        # Center share = 2400 * 0.30 = 720 EGP
        
        result = self.service.calculate_teacher_settlement(
            teacher_id=self.teacher.id,
            month='2024-01'
        )
        
        self.assertEqual(result['total_revenue'], 2400)
        self.assertEqual(result['center_share'], 720)
        self.assertEqual(result['teacher_share'], 1680)
        self.assertEqual(result['total_sessions'], 4)
        self.assertEqual(result['total_students'], 2)
    
    def test_calculate_group_revenue(self):
        """Test group revenue calculation"""
        result = self.service.calculate_group_revenue(
            group_id=self.group.id,
            month='2024-01'
        )
        
        self.assertEqual(result['total_revenue'], 2400)
        self.assertEqual(result['total_sessions'], 4)
        self.assertEqual(result['total_students'], 2)
    
    def test_calculate_settlement_with_different_center_percentage(self):
        """Test settlement with different center percentage"""
        # Update group center percentage
        self.group.center_percentage = 40
        self.group.save()
        
        # Teacher share = 2400 - (2400 * 0.40) = 1440 EGP
        # Center share = 2400 * 0.40 = 960 EGP
        
        result = self.service.calculate_teacher_settlement(
            teacher_id=self.teacher.id,
            month='2024-01'
        )
        
        self.assertEqual(result['center_share'], 960)
        self.assertEqual(result['teacher_share'], 1440)
    
    def test_calculate_settlement_with_symbolic_students(self):
        """Test settlement with symbolic students"""
        # Create symbolic student
        symbolic_student = Student.objects.create(
            name='Symbolic Student',
            phone='01234567893',
            group=self.group,
            financial_status='symbolic',
            barcode='1234567892'
        )
        
        # Add attendance for symbolic student
        session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date()
        )
        
        Attendance.objects.create(
            student=symbolic_student,
            session=session,
            status='present'
        )
        
        # Total revenue = 2400 + 100 = 2500 EGP
        # Teacher share = 2500 - (2500 * 0.30) = 1750 EGP
        
        result = self.service.calculate_teacher_settlement(
            teacher_id=self.teacher.id,
            month='2024-01'
        )
        
        self.assertEqual(result['total_revenue'], 2500)
        self.assertEqual(result['total_students'], 3)


class PaymentModelTest(TestCase):
    
    def setUp(self):
        """Set up test data"""
        self.group = Group.objects.create(
            name='Test Group',
            subject='Math',
            grade='Grade 1'
        )
        
        self.student = Student.objects.create(
            name='Test Student',
            phone='01234567890',
            group=self.group,
            financial_status='normal',
            barcode='1234567890'
        )
        
        self.payment = Payment.objects.create(
            student=self.student,
            month='2024-01',
            amount_due=300,
            amount_paid=0,
            status='unpaid'
        )
    
    def test_payment_creation(self):
        """Test payment creation"""
        self.assertEqual(self.payment.month, '2024-01')
        self.assertEqual(self.payment.amount_due, 300)
        self.assertEqual(self.payment.status, 'unpaid')
    
    def test_payment_status_unpaid(self):
        """Test unpaid status"""
        self.assertEqual(self.payment.status, 'unpaid')
    
    def test_payment_status_partial(self):
        """Test partial payment status"""
        self.payment.amount_paid = 100
        self.payment.save()
        self.assertEqual(self.payment.status, 'partial')
    
    def test_payment_status_paid(self):
        """Test paid status"""
        self.payment.amount_paid = 300
        self.payment.save()
        self.assertEqual(self.payment.status, 'paid')
    
    def test_str_representation(self):
        """Test string representation"""
        self.assertEqual(str(self.payment), 'Test Student - 2024-01')
