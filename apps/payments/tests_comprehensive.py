"""
Comprehensive Unit Tests for Payments App
"""

import pytest
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import datetime
from apps.accounts.models import User
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group
from apps.payments.models import Payment, TeacherSettlement
from apps.payments.services import CreditService, SettlementService


class PaymentModelTestCase(TestCase):
    """Test Payment model"""
    
    def setUp(self):
        self.student = Student.objects.create(
            full_name='Test Student',
            student_code='TEST001',
            is_active=True
        )
        
        self.teacher = Teacher.objects.create(
            teacher_name='Test Teacher',
            is_active=True
        )
        
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            session_price=100.00,
            is_active=True
        )
        
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            is_active=True
        )
    
    def test_payment_creation(self):
        """Test payment is created correctly"""
        payment = Payment.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('400.00'),
            amount_paid=Decimal('0.00'),
            status='unpaid'
        )
        self.assertEqual(payment.status, 'unpaid')
        self.assertEqual(payment.amount_due, Decimal('400.00'))
    
    def test_payment_partial_payment(self):
        """Test partial payment"""
        payment = Payment.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('400.00'),
            amount_paid=Decimal('200.00'),
            status='partial'
        )
        self.assertEqual(payment.status, 'partial')
        self.assertEqual(payment.remaining_balance, Decimal('200.00'))
    
    def test_payment_full_payment(self):
        """Test full payment"""
        payment = Payment.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('400.00'),
            amount_paid=Decimal('400.00'),
            status='paid'
        )
        self.assertEqual(payment.status, 'paid')
        self.assertEqual(payment.remaining_balance, Decimal('0.00'))
    
    def test_payment_string_representation(self):
        """Test __str__ method"""
        payment = Payment.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('400.00')
        )
        self.assertIn(self.student.full_name, str(payment))


class CreditServiceTestCase(TestCase):
    """Test CreditService"""
    
    def setUp(self):
        self.student = Student.objects.create(
            full_name='Test Student',
            student_code='TEST001',
            is_active=True
        )
        
        self.teacher = Teacher.objects.create(
            teacher_name='Test Teacher',
            is_active=True
        )
        
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            session_price=100.00,
            is_active=True
        )
        
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            is_active=True
        )
    
    def test_check_payment_status_no_payment(self):
        """Test payment status check with no payment"""
        result = CreditService.check_payment_status(
            self.student.student_id,
            self.group.group_id
        )
        self.assertFalse(result['is_paid'])
    
    def test_check_payment_status_paid(self):
        """Test payment status check with paid payment"""
        Payment.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('400.00'),
            amount_paid=Decimal('400.00'),
            status='paid'
        )
        
        result = CreditService.check_payment_status(
            self.student.student_id,
            self.group.group_id
        )
        self.assertTrue(result['is_paid'])


class PaymentViewsTestCase(TestCase):
    """Test payment views"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='SecurePass123!',
            role='supervisor'
        )
        self.client.login(username='testuser', password='SecurePass123!')
        
        self.student = Student.objects.create(
            full_name='Test Student',
            student_code='TEST001',
            is_active=True
        )
        
        self.teacher = Teacher.objects.create(
            teacher_name='Test Teacher',
            is_active=True
        )
        
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            session_price=100.00,
            is_active=True
        )
        
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            is_active=True
        )
        
        self.payment = Payment.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('400.00'),
            amount_paid=Decimal('0.00'),
            status='unpaid'
        )
    
    def test_payment_list_view(self):
        """Test payment list view"""
        response = self.client.get(reverse('payments:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.full_name)
    
    def test_record_payment_valid(self):
        """Test recording a valid payment"""
        response = self.client.post(
            reverse('payments:record', args=[self.payment.payment_id]),
            {'amount': '200.00'}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Verify payment was updated
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('200.00'))
        self.assertEqual(self.payment.status, 'partial')
    
    def test_record_payment_invalid_amount(self):
        """Test recording payment with invalid amount"""
        response = self.client.post(
            reverse('payments:record', args=[self.payment.payment_id]),
            {'amount': '-100.00'}
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
    
    def test_record_payment_nonexistent(self):
        """Test recording payment for nonexistent payment"""
        response = self.client.post(
            reverse('payments:record', args=[99999]),
            {'amount': '100.00'}
        )
        self.assertEqual(response.status_code, 404)


class SettlementServiceTestCase(TestCase):
    """Test SettlementService"""
    
    def setUp(self):
        self.teacher = Teacher.objects.create(
            teacher_name='Test Teacher',
            commission_rate=Decimal('0.50'),  # 50%
            is_active=True
        )
        
        self.group = Group.objects.create(
            group_name='Test Group',
            teacher=self.teacher,
            session_price=Decimal('100.00'),
            is_active=True
        )
    
    def test_calculate_teacher_settlement(self):
        """Test teacher settlement calculation"""
        year = timezone.now().year
        month = timezone.now().month
        
        result = SettlementService.calculate_teacher_settlement(
            self.teacher.teacher_id,
            year,
            month
        )
        
        self.assertTrue(result['success'])
        self.assertIn('data', result)
        self.assertIn('total_sessions', result['data'])
