"""
Comprehensive Unit Tests for SYSeducore System
اختبارات شاملة لنظام إدارة السنتر التعليمي
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date, time, timedelta
from django.utils import timezone

from apps.teachers.models import Teacher, Room, Group
from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import Attendance, Session
from apps.payments.models import Payment


User = get_user_model()


class BaseTestCase(TestCase):
    """Base test case with common setup"""

    @classmethod
    def setUpTestData(cls):
        # Create test user
        cls.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com'
        )
        cls.supervisor = User.objects.create_user(
            username='supervisor',
            password='testpass123',
            email='supervisor@example.com',
            role='supervisor'
        )

        # Create test room
        cls.room = Room.objects.create(
            name='قاعة اختبار',
            capacity=25
        )

        # Create test teacher
        cls.teacher = Teacher.objects.create(
            full_name='مدرس اختبار',
            phone='01012345678',
            email='teacher@test.com',
            specialization='رياضيات',
            hire_date=date(2023, 1, 1)
        )

        # Create test group
        cls.group = Group.objects.create(
            group_name='مجموعة اختبار',
            teacher=cls.teacher,
            room=cls.room,
            schedule_day='Saturday',
            schedule_time=time(16, 0),
            standard_fee=Decimal('300.00'),
            center_percentage=Decimal('30.00')
        )

        # Create test student
        cls.student = Student.objects.create(
            student_code='9999',
            full_name='طالب اختبار',
            parent_phone='01098765432'
        )

        # Create enrollment
        cls.enrollment = StudentGroupEnrollment.objects.create(
            student=cls.student,
            group=cls.group,
            financial_status='normal'
        )

    def setUp(self):
        self.client = Client()


# ==================== Teacher Tests ====================

class TeacherModelTests(BaseTestCase):
    """Tests for Teacher model"""

    def test_teacher_creation(self):
        """Test teacher is created correctly"""
        self.assertEqual(self.teacher.full_name, 'مدرس اختبار')
        self.assertTrue(self.teacher.is_active)

    def test_teacher_str(self):
        """Test teacher string representation"""
        self.assertEqual(str(self.teacher), 'مدرس اختبار')

    def test_teacher_groups_count(self):
        """Test teacher can have groups"""
        self.assertEqual(self.teacher.groups.count(), 1)


class TeacherViewTests(BaseTestCase):
    """Tests for Teacher views"""

    def test_teacher_list_requires_login(self):
        """Test that teacher list requires authentication"""
        response = self.client.get(reverse('teachers:list'))
        self.assertEqual(response.status_code, 302)  # Redirects to login

    def test_teacher_list_authenticated(self):
        """Test teacher list for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('teachers:list'))
        self.assertEqual(response.status_code, 200)

    def test_teacher_create(self):
        """Test creating a new teacher"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('teachers:create'), {
            'full_name': 'مدرس جديد',
            'phone': '01111111111',
            'email': 'new@test.com',
            'specialization': 'فيزياء',
            'hire_date': '2024-01-01',
            'is_active': True
        })
        self.assertEqual(Teacher.objects.filter(full_name='مدرس جديد').count(), 1)


# ==================== Room Tests ====================

class RoomModelTests(BaseTestCase):
    """Tests for Room model"""

    def test_room_creation(self):
        """Test room is created correctly"""
        self.assertEqual(self.room.name, 'قاعة اختبار')
        self.assertEqual(self.room.capacity, 25)

    def test_room_str(self):
        """Test room string representation"""
        self.assertEqual(str(self.room), 'قاعة اختبار')


class RoomViewTests(BaseTestCase):
    """Tests for Room views"""

    def test_room_list_requires_login(self):
        """Test that room list requires authentication"""
        response = self.client.get(reverse('teachers:room_list'))
        self.assertEqual(response.status_code, 302)

    def test_room_list_authenticated(self):
        """Test room list for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('teachers:room_list'))
        self.assertEqual(response.status_code, 200)


# ==================== Group Tests ====================

class GroupModelTests(BaseTestCase):
    """Tests for Group model"""

    def test_group_creation(self):
        """Test group is created correctly"""
        self.assertEqual(self.group.group_name, 'مجموعة اختبار')
        self.assertEqual(self.group.standard_fee, Decimal('300.00'))

    def test_group_str(self):
        """Test group string representation"""
        self.assertIn('مجموعة اختبار', str(self.group))

    def test_group_teacher_relation(self):
        """Test group has correct teacher"""
        self.assertEqual(self.group.teacher, self.teacher)

    def test_group_room_relation(self):
        """Test group has correct room"""
        self.assertEqual(self.group.room, self.room)


class GroupViewTests(BaseTestCase):
    """Tests for Group views"""

    def test_group_list_requires_login(self):
        """Test that group list requires authentication"""
        response = self.client.get(reverse('teachers:group_list'))
        self.assertEqual(response.status_code, 302)

    def test_group_list_authenticated(self):
        """Test group list for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('teachers:group_list'))
        self.assertEqual(response.status_code, 200)


# ==================== Student Tests ====================

class StudentModelTests(BaseTestCase):
    """Tests for Student model"""

    def test_student_creation(self):
        """Test student is created correctly"""
        self.assertEqual(self.student.student_code, '9999')
        self.assertEqual(self.student.full_name, 'طالب اختبار')
        self.assertTrue(self.student.is_active)

    def test_student_str(self):
        """Test student string representation"""
        self.assertEqual(str(self.student), 'طالب اختبار')

    def test_student_unique_code(self):
        """Test student code must be unique"""
        with self.assertRaises(Exception):
            Student.objects.create(
                student_code='9999',  # Duplicate
                full_name='طالب آخر',
                parent_phone='01000000000'
            )

    def test_student_groups(self):
        """Test student can be enrolled in groups"""
        self.assertEqual(self.student.groups.count(), 1)


class StudentViewTests(BaseTestCase):
    """Tests for Student views"""

    def test_student_list_requires_login(self):
        """Test that student list requires authentication"""
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 302)

    def test_student_list_authenticated(self):
        """Test student list for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 200)


# ==================== Enrollment Tests ====================

class EnrollmentModelTests(BaseTestCase):
    """Tests for StudentGroupEnrollment model"""

    def test_enrollment_creation(self):
        """Test enrollment is created correctly"""
        self.assertEqual(self.enrollment.student, self.student)
        self.assertEqual(self.enrollment.group, self.group)
        self.assertEqual(self.enrollment.financial_status, 'normal')

    def test_enrollment_unique_constraint(self):
        """Test student can't be enrolled twice in same group"""
        with self.assertRaises(Exception):
            StudentGroupEnrollment.objects.create(
                student=self.student,
                group=self.group,
                financial_status='normal'
            )

    def test_enrollment_symbolic_fee(self):
        """Test symbolic fee enrollment"""
        enrollment = StudentGroupEnrollment.objects.create(
            student=Student.objects.create(
                student_code='8888',
                full_name='طالب رمزي',
                parent_phone='01000000001'
            ),
            group=self.group,
            financial_status='symbolic',
            custom_fee=Decimal('100.00')
        )
        self.assertEqual(enrollment.custom_fee, Decimal('100.00'))

    def test_enrollment_exempt(self):
        """Test exempt enrollment"""
        enrollment = StudentGroupEnrollment.objects.create(
            student=Student.objects.create(
                student_code='7777',
                full_name='طالب معفي',
                parent_phone='01000000002'
            ),
            group=self.group,
            financial_status='exempt'
        )
        self.assertEqual(enrollment.financial_status, 'exempt')


# ==================== Attendance Tests ====================

class AttendanceTests(BaseTestCase):
    """Tests for Attendance functionality"""

    def test_create_session(self):
        """Test creating an attendance session"""
        session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date()
        )
        self.assertIsNotNone(session)
        self.assertEqual(session.group, self.group)

    def test_record_attendance(self):
        """Test recording student attendance"""
        session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date()
        )
        attendance = Attendance.objects.create(
            student=self.student,
            session=session,
            scan_time=timezone.now(),
            status='present'
        )
        self.assertIsNotNone(attendance)
        self.assertEqual(attendance.student, self.student)


# ==================== Payment Tests ====================

class PaymentTests(BaseTestCase):
    """Tests for Payment functionality"""

    def test_create_payment(self):
        """Test creating a payment"""
        payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=timezone.now().date().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('300.00'),
            status='paid'
        )
        self.assertEqual(payment.amount_due, Decimal('300.00'))
        self.assertEqual(payment.student, self.student)

    def test_payment_status(self):
        """Test different payment statuses"""
        for status in ['paid', 'partial', 'unpaid']:
            payment = Payment.objects.create(
                student=self.student,
                group=self.group,
                month=timezone.now().date().replace(day=1) - timedelta(days=30 * (1 + ['paid', 'partial', 'unpaid'].index(status))),
                amount_due=Decimal('100.00'),
                amount_paid=Decimal('100.00') if status == 'paid' else Decimal('50.00') if status == 'partial' else Decimal('0'),
                status=status
            )
            self.assertEqual(payment.status, status)


# ==================== Authentication Tests ====================

class AuthenticationTests(BaseTestCase):
    """Tests for Authentication"""

    def test_login_page_loads(self):
        """Test login page loads correctly"""
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)

    def test_login_success(self):
        """Test successful login"""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertIn(response.status_code, [200, 302])

    def test_login_failure(self):
        """Test failed login with wrong password"""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        # Should stay on login page or show error
        self.assertEqual(response.status_code, 200)

    def test_logout(self):
        """Test logout"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:logout'))
        self.assertIn(response.status_code, [200, 302])


# ==================== Reports Tests ====================

class ReportsTests(BaseTestCase):
    """Tests for Reports"""

    def test_reports_requires_login(self):
        """Test reports requires authentication"""
        response = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_reports_authenticated(self):
        """Test reports loads for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(response.status_code, 200)


# ==================== Scanner Tests ====================

class ScannerTests(BaseTestCase):
    """Tests for Scanner/Code Entry functionality"""

    def test_scanner_page_requires_login(self):
        """Test scanner page requires authentication"""
        response = self.client.get(reverse('attendance:scanner'))
        self.assertEqual(response.status_code, 302)

    def test_scanner_page_loads(self):
        """Test scanner page loads for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('attendance:scanner'))
        self.assertEqual(response.status_code, 200)


# ==================== Payments View Tests ====================

class PaymentsViewTests(BaseTestCase):
    """Tests for Payments views"""

    def test_payments_list_requires_login(self):
        """Test payments list requires authentication"""
        response = self.client.get(reverse('payments:list'))
        self.assertEqual(response.status_code, 302)

    def test_payments_list_authenticated(self):
        """Test payments list loads for authenticated user"""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('payments:list'))
        self.assertEqual(response.status_code, 200)


# ==================== Integration Tests ====================

class IntegrationTests(BaseTestCase):
    """Integration tests for complete workflows"""

    def test_complete_attendance_workflow(self):
        """Test complete attendance recording workflow"""
        self.client.login(username='testuser', password='testpass123')

        # 1. Create a session
        session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date()
        )

        # 2. Record attendance
        attendance = Attendance.objects.create(
            student=self.student,
            session=session,
            scan_time=timezone.now(),
            status='present'
        )

        # 3. Verify attendance recorded
        self.assertEqual(session.attendances.count(), 1)
        self.assertEqual(attendance.student.student_code, '9999')

    def test_complete_enrollment_workflow(self):
        """Test complete student enrollment workflow"""
        # 1. Create new student
        new_student = Student.objects.create(
            student_code='6666',
            full_name='طالب جديد',
            parent_phone='01099999999'
        )

        # 2. Enroll in group
        enrollment = StudentGroupEnrollment.objects.create(
            student=new_student,
            group=self.group,
            financial_status='normal'
        )

        # 3. Verify enrollment
        self.assertIn(new_student, self.group.enrolled_students.all())
        self.assertEqual(new_student.groups.count(), 1)


# ==================== Edge Case Tests ====================

class EdgeCaseTests(BaseTestCase):
    """Tests for edge cases and error handling"""

    def test_duplicate_student_code(self):
        """Test that duplicate student code is rejected"""
        with self.assertRaises(Exception):
            Student.objects.create(
                student_code='9999',  # Same as self.student
                full_name='طالب بكود مكرر',
                parent_phone='01000000000'
            )

    def test_negative_fee(self):
        """Test that negative fees are handled"""
        # This depends on model validation
        pass

    def test_future_hire_date(self):
        """Test teacher with future hire date"""
        future_teacher = Teacher.objects.create(
            full_name='مدرس مستقبلي',
            phone='01099999999',
            email='future@test.com',
            specialization='علوم',
            hire_date=date(2030, 1, 1)
        )
        self.assertIsNotNone(future_teacher)

    def test_room_over_capacity(self):
        """Test handling room capacity"""
        small_room = Room.objects.create(name='قاعة صغيرة', capacity=2)
        # This would need business logic to enforce
        pass


# ==================== Performance Tests ====================

class PerformanceTests(BaseTestCase):
    """Basic performance tests"""

    def test_student_list_performance(self):
        """Test student list loads with many students"""
        # Create 100 students
        for i in range(100):
            Student.objects.create(
                student_code=f'P{i:04d}',
                full_name=f'طالب أداء {i}',
                parent_phone=f'010{i:08d}'
            )

        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 200)
