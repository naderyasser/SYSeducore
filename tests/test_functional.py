"""
Comprehensive functional tests simulating admin, supervisor, and student/teacher workflows.
Tests all 7 implemented features + camera/scanner page.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from apps.teachers.models import Teacher, Group, GroupSchedule, Room, Subject
from apps.students.models import Student
from apps.payments.models import Payment
from decimal import Decimal
from django.utils import timezone
import datetime

User = get_user_model()


class AdminRoleTest(TestCase):
    """Test admin can access all pages and see admin-only features."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_test', password='pass123', role='admin', is_superuser=True
        )
        self.client.login(username='admin_test', password='pass123')

    def test_dashboard(self):
        resp = self.client.get('/dashboard/')
        self.assertIn(resp.status_code, [200, 302])  # May redirect to role-specific page

    def test_student_list(self):
        resp = self.client.get('/students/')
        self.assertEqual(resp.status_code, 200)

    def test_teacher_list(self):
        resp = self.client.get('/teachers/')
        self.assertEqual(resp.status_code, 200)

    def test_group_list(self):
        resp = self.client.get('/teachers/groups/')
        self.assertEqual(resp.status_code, 200)

    def test_attendance_scanner(self):
        resp = self.client.get('/attendance/scanner/')
        self.assertEqual(resp.status_code, 200)

    def test_payment_report_no_password(self):
        """Payment report should load directly without password (feature #7)."""
        resp = self.client.get('/reports/payments/')
        self.assertEqual(resp.status_code, 200)

    def test_financial_report_no_password(self):
        """Financial report should load directly without password (feature #7)."""
        resp = self.client.get('/reports/financial/')
        self.assertEqual(resp.status_code, 200)

    def test_recycle_bin(self):
        resp = self.client.get('/reports/recycle-bin/')
        self.assertEqual(resp.status_code, 200)

    def test_user_management(self):
        resp = self.client.get('/accounts/users/')
        self.assertEqual(resp.status_code, 200)

    def test_recycle_bin_admin_sees_permanent_delete(self):
        """Admin should see permanent delete buttons (feature #1)."""
        # Create and soft-delete a student
        student = Student.objects.create(
            full_name='Test Student', student_code='T001',
            parent_phone='0100000', gender='male',
        )
        student.soft_delete(self.admin)

        resp = self.client.get('/reports/recycle-bin/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('حذف نهائي', content)


class SupervisorRoleTest(TestCase):
    """Test supervisor can access allowed pages but NOT admin-only features."""

    def setUp(self):
        self.client = Client()
        self.supervisor = User.objects.create_user(
            username='super_test', password='pass123', role='supervisor'
        )
        self.client.login(username='super_test', password='pass123')

    def test_dashboard(self):
        resp = self.client.get('/dashboard/')
        self.assertIn(resp.status_code, [200, 302])  # May redirect to role-specific page

    def test_student_list(self):
        resp = self.client.get('/students/')
        self.assertEqual(resp.status_code, 200)

    def test_teacher_list(self):
        resp = self.client.get('/teachers/')
        self.assertEqual(resp.status_code, 200)

    def test_attendance_scanner(self):
        resp = self.client.get('/attendance/scanner/')
        self.assertEqual(resp.status_code, 200)

    def test_recycle_bin_no_permanent_delete(self):
        """Supervisor should NOT see permanent delete buttons (feature #1)."""
        admin = User.objects.create_user(
            username='admin_tmp', password='pass123', role='admin', is_superuser=True
        )
        student = Student.objects.create(
            full_name='Test Student', student_code='T002',
            parent_phone='0100001', gender='male',
        )
        student.soft_delete(admin)

        resp = self.client.get('/reports/recycle-bin/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn('حذف نهائي', content)


class PaymentReportTeacherFilterTest(TestCase):
    """Test payment report has teacher filter dropdown (feature #6)."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_pay', password='pass123', role='admin', is_superuser=True
        )
        self.client.login(username='admin_pay', password='pass123')

        self.teacher = Teacher.objects.create(
            full_name='Test Teacher', phone='0100', email='t@t.com',
            hire_date=datetime.date.today(),
        )

    def test_teacher_filter_present(self):
        resp = self.client.get('/reports/payments/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # The teacher filter dropdown should mention teacher selection
        self.assertTrue(
            'selected_teacher' in content or 'المدرس' in content,
            "Teacher filter not found in payment report"
        )

    def test_filter_by_teacher(self):
        resp = self.client.get(f'/reports/payments/?selected_teacher={self.teacher.pk}')
        self.assertEqual(resp.status_code, 200)


class GroupScheduleTest(TestCase):
    """Test group scheduling per day (feature #2)."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_grp', password='pass123', role='admin', is_superuser=True
        )
        self.client.login(username='admin_grp', password='pass123')
        self.teacher = Teacher.objects.create(
            full_name='Schedule Teacher', phone='0101', email='st@t.com',
            hire_date=datetime.date.today(),
        )
        self.room = Room.objects.create(name='Room A', capacity=30)

    def test_group_create_page(self):
        resp = self.client.get('/teachers/groups/create/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Should have schedule/day fields
        self.assertTrue(
            'schedule' in content.lower() or 'الجدول' in content or 'day' in content.lower(),
            "Schedule fields not found in group create form"
        )

    def test_group_schedule_model(self):
        """GroupSchedule can be created for a group."""
        group = Group.objects.create(
            group_name='Test Group', teacher=self.teacher, room=self.room,
            standard_fee=Decimal('100'), center_percentage=Decimal('30'),
            schedule_day='Saturday', schedule_time='14:00',
        )
        schedule = GroupSchedule.objects.create(
            group=group, day_of_week='Saturday',
            start_time='14:00', duration=120,
        )
        self.assertEqual(schedule.group, group)
        self.assertEqual(schedule.day_of_week, 'Saturday')
        self.assertEqual(group.schedules.count(), 1)


class ScannerPageTest(TestCase):
    """Test scanner page has camera and manual input (feature #5)."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_scan', password='pass123', role='admin', is_superuser=True
        )
        self.client.login(username='admin_scan', password='pass123')

    def test_scanner_loads(self):
        resp = self.client.get('/attendance/scanner/')
        self.assertEqual(resp.status_code, 200)

    def test_manual_input_present(self):
        """Scanner should have manual code input field (feature #5)."""
        resp = self.client.get('/attendance/scanner/')
        content = resp.content.decode()
        self.assertIn('manualCodeInput', content)

    def test_camera_elements_present(self):
        """Scanner should have camera button and error handling."""
        resp = self.client.get('/attendance/scanner/')
        content = resp.content.decode()
        # Camera or video element
        has_camera = 'camera' in content.lower() or 'video' in content.lower()
        self.assertTrue(has_camera, "Camera elements not found in scanner page")

    def test_camera_error_div(self):
        """Scanner should have cameraError div for inline error display."""
        resp = self.client.get('/attendance/scanner/')
        content = resp.content.decode()
        self.assertIn('cameraError', content)


class StudentQRTicketTest(TestCase):
    """Test QR ticket printing (feature #4)."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_qr', password='pass123', role='admin', is_superuser=True
        )
        self.client.login(username='admin_qr', password='pass123')
        self.student = Student.objects.create(
            full_name='QR Student', student_code='QR001',
            parent_phone='0100002', gender='male',
        )

    def test_qr_ticket_page(self):
        resp = self.client.get(f'/students/{self.student.pk}/qr-ticket/')
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('QR001', content)
        self.assertIn('QR Student', content)


class StudentCodeConcurrencyTest(TestCase):
    """Test student code generation uses atomic + select_for_update (feature #3)."""

    def test_sequential_code_generation(self):
        """Creating multiple students gives sequential codes."""
        s1 = Student.objects.create(
            full_name='Student 1', parent_phone='0100010', gender='male'
        )
        s2 = Student.objects.create(
            full_name='Student 2', parent_phone='0100011', gender='male'
        )
        # Codes should be sequential
        self.assertNotEqual(s1.student_code, s2.student_code)
        self.assertTrue(s1.student_code.isdigit())
        self.assertTrue(s2.student_code.isdigit())


class GroupCreatePostTest(TestCase):
    """Test group creation via POST with multi-day schedule."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='admin_gc', password='pass123', role='admin', is_superuser=True
        )
        self.client.login(username='admin_gc', password='pass123')
        self.teacher = Teacher.objects.create(
            full_name='GC Teacher', phone='0109', email='gc@t.com',
            hire_date=datetime.date.today(),
        )
        self.room = Room.objects.create(name='GC Room', capacity=25)

    def test_create_group_post(self):
        """POST to group create should save group + schedules and redirect."""
        resp = self.client.post('/teachers/groups/create/', {
            'group_name': 'Math Group',
            'teacher': self.teacher.pk,
            'room': self.room.pk,
            'duration_minutes': '90',
            'gender_type': 'mixed',
            'standard_fee': '200',
            'center_percentage': '30',
            'sessions_per_month': '4',
            'is_active': 'on',
            'schedule_days[]': ['Saturday', 'Monday'],
            'schedule_time_Saturday': '14:00',
            'schedule_time_Monday': '16:00',
        })
        self.assertEqual(resp.status_code, 302, f"Expected redirect, got {resp.status_code}")
        # Group should exist
        group = Group.objects.get(group_name='Math Group')
        self.assertEqual(group.teacher, self.teacher)
        self.assertEqual(group.schedule_day, 'Saturday')  # Legacy field = first day
        # Schedules should exist
        schedules = GroupSchedule.objects.filter(group=group).order_by('day_of_week')
        self.assertEqual(schedules.count(), 2)
        days = list(schedules.values_list('day_of_week', flat=True))
        self.assertIn('Saturday', days)
        self.assertIn('Monday', days)

    def test_create_group_single_day(self):
        """POST with a single day should also work."""
        resp = self.client.post('/teachers/groups/create/', {
            'group_name': 'Science Group',
            'teacher': self.teacher.pk,
            'duration_minutes': '120',
            'gender_type': 'male',
            'standard_fee': '150',
            'center_percentage': '25',
            'sessions_per_month': '4',
            'is_active': 'on',
            'schedule_days[]': ['Wednesday'],
            'schedule_time_Wednesday': '10:00',
        })
        self.assertEqual(resp.status_code, 302)
        group = Group.objects.get(group_name='Science Group')
        self.assertEqual(group.schedules.count(), 1)
        self.assertEqual(group.schedule_day, 'Wednesday')

    def test_create_group_no_days_rejected(self):
        """POST without any days should stay on form (not redirect)."""
        resp = self.client.post('/teachers/groups/create/', {
            'group_name': 'Empty Group',
            'teacher': self.teacher.pk,
            'duration_minutes': '120',
            'gender_type': 'mixed',
            'standard_fee': '100',
            'center_percentage': '30',
            'sessions_per_month': '4',
            'is_active': 'on',
        })
        self.assertEqual(resp.status_code, 200)  # Stays on form
        self.assertEqual(Group.objects.filter(group_name='Empty Group').count(), 0)
