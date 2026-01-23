"""
Tests for Student Model
"""

from django.test import TestCase
from django.utils import timezone
from apps.students.models import Student
from apps.teachers.models import Group


class StudentModelTest(TestCase):
    
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
            parent_phone='09876543210',
            group=self.group,
            financial_status='normal',
            barcode='1234567890'
        )
    
    def test_student_creation(self):
        """Test student creation"""
        self.assertEqual(self.student.name, 'Test Student')
        self.assertEqual(self.student.financial_status, 'normal')
        self.assertEqual(self.student.barcode, '1234567890')
    
    def test_get_monthly_fee_normal(self):
        """Test monthly fee for normal status"""
        self.assertEqual(self.student.get_monthly_fee(), 300)
    
    def test_get_monthly_fee_symbolic(self):
        """Test monthly fee for symbolic status"""
        self.student.financial_status = 'symbolic'
        self.student.save()
        self.assertEqual(self.student.get_monthly_fee(), 100)
    
    def test_get_monthly_fee_exempt(self):
        """Test monthly fee for exempt status"""
        self.student.financial_status = 'exempt'
        self.student.save()
        self.assertEqual(self.student.get_monthly_fee(), 0)
    
    def test_str_representation(self):
        """Test string representation"""
        self.assertEqual(str(self.student), 'Test Student')
    
    def test_student_ordering(self):
        """Test students are ordered by name"""
        student2 = Student.objects.create(
            name='A Student',
            phone='01234567891',
            group=self.group,
            financial_status='normal',
            barcode='1234567891'
        )
        
        students = list(Student.objects.all())
        self.assertEqual(students[0].name, 'A Student')
        self.assertEqual(students[1].name, 'Test Student')
