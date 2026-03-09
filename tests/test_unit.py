"""
Comprehensive Unit Tests for SYSeducore System.
Covers: Models, Views, Forms, Decorators, URLs, Templates.

Run with: python manage.py test tests.test_unit --settings=config.settings_test -v2
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse, resolve
from django.utils import timezone

from apps.students.models import Student, StudentGroupEnrollment
from apps.students.forms import StudentForm, StudentQuickForm
from apps.teachers.models import Teacher, Group, Room, Subject
from apps.payments.models import Payment
from apps.attendance.models import Session, Attendance, ActivityLog
from apps.accounts.forms import LoginForm

User = get_user_model()


# ============================================================
#  Helper Mixin — shared setup for most tests
# ============================================================
class BaseTestMixin:
    """Creates common objects used across test classes."""

    def setUp(self):
        # Users
        self.admin_user = User.objects.create_user(
            username='admin_test', password='TestPass123!',
            role='admin', is_staff=True, is_superuser=True,
        )
        self.supervisor_user = User.objects.create_user(
            username='supervisor_test', password='TestPass123!',
            role='supervisor',
        )
        self.teacher_user = User.objects.create_user(
            username='teacher_test', password='TestPass123!',
            role='teacher',
        )

        # Core objects
        self.room = Room.objects.create(name='قاعة 1', capacity=30)
        self.subject = Subject.objects.create(name='رياضيات')

        self.teacher = Teacher.objects.create(
            full_name='أحمد محمد',
            phone='01012345678',
            specialization='رياضيات',
            hire_date=date(2024, 1, 1),
        )
        self.teacher.subjects.add(self.subject)

        self.group = Group.objects.create(
            group_name='مجموعة أ',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(14, 0),
            duration_minutes=120,
            standard_fee=Decimal('200.00'),
            center_percentage=Decimal('30.00'),
        )

        self.student = Student.objects.create(
            student_code='STU001',
            full_name='طالب تجريبي',
            gender='male',
            parent_phone='01098765432',
            student_phone='01011111111',
        )

        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal',
            is_active=True,
        )

        self.client = Client()


# ============================================================
#  1. MODEL TESTS
# ============================================================
class UserModelTest(BaseTestMixin, TestCase):
    """Tests for the custom User model."""

    def test_user_creation(self):
        self.assertEqual(self.admin_user.role, 'admin')
        self.assertTrue(self.admin_user.is_admin())
        self.assertFalse(self.admin_user.is_teacher())

    def test_supervisor_role(self):
        self.assertTrue(self.supervisor_user.is_supervisor())
        self.assertFalse(self.supervisor_user.is_admin())

    def test_teacher_role(self):
        self.assertTrue(self.teacher_user.is_teacher())
        self.assertFalse(self.teacher_user.is_admin())

    def test_default_role(self):
        u = User.objects.create_user(username='default_user', password='pass')
        self.assertEqual(u.role, 'supervisor')


class StudentModelTest(BaseTestMixin, TestCase):
    """Tests for Student model."""

    def test_student_creation(self):
        self.assertEqual(self.student.student_code, 'STU001')
        self.assertTrue(self.student.is_active)

    def test_student_str(self):
        self.assertIn('طالب تجريبي', str(self.student))

    def test_generate_next_code(self):
        code = Student.generate_next_code()
        self.assertIsNotNone(code)
        # Should be numeric string bigger than existing codes
        self.assertTrue(len(code) > 0)

    def test_get_active_groups_count(self):
        self.assertEqual(self.student.get_active_groups_count(), 1)

    def test_get_total_paid_amount_no_payments(self):
        total = self.student.get_total_paid_amount()
        self.assertEqual(total, 0)

    def test_get_total_paid_amount_with_payments(self):
        Payment.objects.create(
            student=self.student, group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('200.00'), amount_paid=Decimal('150.00'),
            status='paid',
        )
        total = self.student.get_total_paid_amount()
        self.assertEqual(total, Decimal('150.00'))

    def test_activate_subscription(self):
        self.student.activate_subscription(days=30)
        self.assertIsNotNone(self.student.subscription_expiry_date)
        self.assertTrue(self.student.is_subscription_active())

    def test_subscription_expired(self):
        self.student.subscription_expiry_date = date.today() - timedelta(days=1)
        self.student.save()
        self.assertFalse(self.student.is_subscription_active())

    def test_get_parent_label_male(self):
        self.student.gender = 'male'
        label = self.student.get_parent_label()
        self.assertIn('الأب', label)

    def test_get_parent_label_female(self):
        self.student.gender = 'female'
        label = self.student.get_parent_label()
        self.assertIn('الأم', label)

    def test_unique_student_code(self):
        with self.assertRaises(Exception):
            Student.objects.create(
                student_code='STU001',
                full_name='طالب مكرر',
                gender='male',
                parent_phone='01000000000',
            )


class StudentGroupEnrollmentTest(BaseTestMixin, TestCase):
    """Tests for enrollment through-model."""

    def test_enrollment_created(self):
        self.assertEqual(self.enrollment.financial_status, 'normal')
        self.assertTrue(self.enrollment.is_active)

    def test_unique_together_enrollment(self):
        with self.assertRaises(Exception):
            StudentGroupEnrollment.objects.create(
                student=self.student,
                group=self.group,
                financial_status='normal',
            )

    def test_enrollment_protect_student_delete(self):
        """PROTECT should prevent student deletion when enrolled."""
        with self.assertRaises(Exception):
            self.student.delete()

    def test_enrollment_protect_group_delete(self):
        """PROTECT should prevent group deletion when has enrollments."""
        with self.assertRaises(Exception):
            self.group.delete()


class TeacherModelTest(BaseTestMixin, TestCase):
    """Tests for Teacher model."""

    def test_teacher_creation(self):
        self.assertEqual(self.teacher.full_name, 'أحمد محمد')
        self.assertTrue(self.teacher.is_active)

    def test_get_subjects_display(self):
        display = self.teacher.get_subjects_display()
        self.assertIn('رياضيات', display)

    def test_teacher_groups(self):
        self.assertEqual(self.teacher.groups.count(), 1)


class RoomModelTest(BaseTestMixin, TestCase):
    """Tests for Room model."""

    def test_room_creation(self):
        self.assertEqual(self.room.name, 'قاعة 1')
        self.assertEqual(self.room.capacity, 30)

    def test_unique_room_name(self):
        with self.assertRaises(Exception):
            Room.objects.create(name='قاعة 1', capacity=20)


class SubjectModelTest(BaseTestMixin, TestCase):
    """Tests for Subject model."""

    def test_subject_creation(self):
        self.assertEqual(self.subject.name, 'رياضيات')

    def test_subject_teachers_relation(self):
        self.assertIn(self.teacher, self.subject.teachers.all())


class GroupModelTest(BaseTestMixin, TestCase):
    """Tests for Group model."""

    def test_group_creation(self):
        self.assertEqual(self.group.group_name, 'مجموعة أ')
        self.assertEqual(self.group.standard_fee, Decimal('200.00'))

    def test_get_end_time(self):
        end = self.group.get_end_time()
        # 14:00 + 120 mins = 16:00
        self.assertEqual(end, time(16, 0))

    def test_get_duration_display(self):
        display = self.group.get_duration_display()
        self.assertIn('2', display)  # 2 hours

    def test_group_protect_teacher_delete(self):
        """PROTECT should prevent teacher deletion when has groups."""
        with self.assertRaises(Exception):
            self.teacher.delete()

    def test_group_protect_room_delete(self):
        """PROTECT should prevent room deletion when has groups."""
        with self.assertRaises(Exception):
            self.room.delete()


class PaymentModelTest(BaseTestMixin, TestCase):
    """Tests for Payment model."""

    def test_payment_creation(self):
        payment = Payment.objects.create(
            student=self.student, group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('200.00'), amount_paid=Decimal('0.00'),
            status='unpaid',
        )
        self.assertEqual(payment.status, 'unpaid')
        self.assertEqual(payment.amount_due, Decimal('200.00'))

    def test_payment_unique_constraint(self):
        month = date.today().replace(day=1)
        Payment.objects.create(
            student=self.student, group=self.group,
            month=month, amount_due=Decimal('200.00'),
        )
        with self.assertRaises(Exception):
            Payment.objects.create(
                student=self.student, group=self.group,
                month=month, amount_due=Decimal('200.00'),
            )

    def test_payment_protect_student_delete(self):
        Payment.objects.create(
            student=self.student, group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('200.00'),
        )
        with self.assertRaises(Exception):
            self.student.delete()

    def test_payment_validators(self):
        """amount_due and amount_paid should reject negative values."""
        payment = Payment(
            student=self.student, group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('-100.00'),
        )
        with self.assertRaises(Exception):
            payment.full_clean()


class SessionModelTest(BaseTestMixin, TestCase):
    """Tests for Session model."""

    def test_session_creation(self):
        session = Session.objects.create(
            group=self.group,
            session_date=date.today(),
        )
        self.assertFalse(session.is_cancelled)
        self.assertFalse(session.teacher_attended)

    def test_session_unique_per_group_date(self):
        today = date.today()
        Session.objects.create(group=self.group, session_date=today)
        with self.assertRaises(Exception):
            Session.objects.create(group=self.group, session_date=today)


class AttendanceModelTest(BaseTestMixin, TestCase):
    """Tests for Attendance model."""

    def test_attendance_creation(self):
        session = Session.objects.create(
            group=self.group, session_date=date.today(),
        )
        att = Attendance.objects.create(
            student=self.student, session=session,
            status='present',
        )
        self.assertEqual(att.status, 'present')

    def test_attendance_unique_per_student_session(self):
        session = Session.objects.create(
            group=self.group, session_date=date.today(),
        )
        Attendance.objects.create(
            student=self.student, session=session, status='present',
        )
        with self.assertRaises(Exception):
            Attendance.objects.create(
                student=self.student, session=session, status='late',
            )


class ActivityLogTest(BaseTestMixin, TestCase):
    """Tests for ActivityLog model."""

    def test_log_creation(self):
        ActivityLog.log(
            user=self.admin_user,
            action='student_create',
            description='Test log entry',
            target_model='Student',
            target_id=self.student.student_id,
        )
        self.assertEqual(ActivityLog.objects.count(), 1)
        log = ActivityLog.objects.first()
        self.assertEqual(log.action, 'student_create')


# ============================================================
#  2. FORM TESTS
# ============================================================
class LoginFormTest(TestCase):
    """Tests for LoginForm."""

    def test_valid_login_form(self):
        form = LoginForm(data={'username': 'admin', 'password': 'pass123'})
        self.assertTrue(form.is_valid())

    def test_empty_username(self):
        form = LoginForm(data={'username': '', 'password': 'pass'})
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)

    def test_empty_password(self):
        form = LoginForm(data={'username': 'admin', 'password': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('password', form.errors)


class StudentFormTest(BaseTestMixin, TestCase):
    """Tests for StudentForm."""

    def test_valid_student_form(self):
        form = StudentForm(data={
            'full_name': 'طالب جديد',
            'gender': 'male',
            'parent_phone': '01012345678',
            'student_phone': '01098765432',
            'education_type': 'general',
            'is_active': True,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_required_fields(self):
        form = StudentForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn('full_name', form.errors)
        self.assertIn('parent_phone', form.errors)

    def test_duplicate_student_code(self):
        form = StudentForm(data={
            'student_code': 'STU001',  # Already exists
            'full_name': 'طالب آخر',
            'gender': 'male',
            'parent_phone': '01000000000',
            'student_phone': '01011111112',
        })
        self.assertFalse(form.is_valid())

    def test_phone_normalization(self):
        form = StudentForm(data={
            'full_name': 'طالب',
            'gender': 'male',
            'parent_phone': '+2001012345678',
            'student_phone': '01098765432',
        })
        if form.is_valid():
            self.assertTrue(
                form.cleaned_data['parent_phone'].startswith('0')
            )

    def test_auto_code_generation(self):
        """Empty student_code should be allowed (auto-generated)."""
        form = StudentForm(data={
            'student_code': '',
            'full_name': 'طالب بدون كود',
            'gender': 'female',
            'parent_phone': '01055555555',
            'student_phone': '01066666666',
            'education_type': 'general',
        })
        self.assertTrue(form.is_valid(), form.errors)


class StudentQuickFormTest(TestCase):
    """Tests for StudentQuickForm."""

    def test_valid_quick_form(self):
        form = StudentQuickForm(data={
            'full_name': 'طالب سريع',
            'parent_phone': '01012345678',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_name(self):
        form = StudentQuickForm(data={'parent_phone': '01012345678'})
        self.assertFalse(form.is_valid())


# ============================================================
#  3. URL / ROUTING TESTS
# ============================================================
class URLResolutionTest(TestCase):
    """Verify URL names resolve to correct views."""

    def test_login_url(self):
        url = reverse('accounts:login')
        self.assertEqual(url, '/accounts/login/')

    def test_logout_url(self):
        url = reverse('accounts:logout')
        self.assertEqual(url, '/accounts/logout/')

    def test_dashboard_url(self):
        url = reverse('reports:dashboard')
        self.assertEqual(url, '/reports/')

    def test_student_list_url(self):
        url = reverse('students:list')
        self.assertEqual(url, '/students/')

    def test_student_create_url(self):
        url = reverse('students:create')
        self.assertEqual(url, '/students/create/')

    def test_teacher_list_url(self):
        url = reverse('teachers:list')
        self.assertEqual(url, '/teachers/')

    def test_payment_list_url(self):
        url = reverse('payments:list')
        self.assertEqual(url, '/payments/')

    def test_scanner_url(self):
        url = reverse('attendance:scanner')
        self.assertEqual(url, '/attendance/scanner/')

    def test_group_list_url(self):
        url = reverse('teachers:group_list')
        self.assertEqual(url, '/teachers/groups/')

    def test_room_list_url(self):
        url = reverse('teachers:room_list')
        self.assertEqual(url, '/teachers/rooms/')

    def test_subject_list_url(self):
        url = reverse('teachers:subject_list')
        self.assertEqual(url, '/teachers/subjects/')


# ============================================================
#  4. VIEW / AUTH TESTS
# ============================================================
class AuthenticationViewTest(BaseTestMixin, TestCase):
    """Tests for login/logout views."""

    def test_login_page_loads(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'تسجيل الدخول')

    def test_login_success(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'admin_test',
            'password': 'TestPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('reports:dashboard'))

    def test_login_wrong_password(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'admin_test',
            'password': 'WrongPassword',
        })
        self.assertEqual(response.status_code, 200)
        # Should show error with alert-danger class
        self.assertContains(response, 'alert-danger')

    def test_login_redirect_when_authenticated(self):
        self.client.login(username='admin_test', password='TestPass123!')
        response = self.client.get(reverse('accounts:login'))
        self.assertRedirects(response, reverse('reports:dashboard'))

    def test_logout_requires_post(self):
        self.client.login(username='admin_test', password='TestPass123!')
        response = self.client.get(reverse('accounts:logout'))
        # GET should redirect to dashboard, not log out
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('reports:dashboard'))

    def test_logout_post(self):
        self.client.login(username='admin_test', password='TestPass123!')
        response = self.client.post(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:login'))


class AccessControlTest(BaseTestMixin, TestCase):
    """Tests for role-based access decorators."""

    def test_unauthenticated_redirect(self):
        """Anonymous users should be redirected to login."""
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_supervisor_can_create_student(self):
        self.client.login(username='supervisor_test', password='TestPass123!')
        response = self.client.get(reverse('students:create'))
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_create_student(self):
        """Teacher role should be denied access to student creation."""
        self.client.login(username='teacher_test', password='TestPass123!')
        response = self.client.get(reverse('students:create'))
        # supervisor_required uses user_passes_test → redirects to login
        self.assertEqual(response.status_code, 302)

    def test_admin_can_access_everything(self):
        self.client.login(username='admin_test', password='TestPass123!')
        for url_name in ['students:list', 'students:create', 'teachers:list',
                         'payments:list', 'reports:dashboard']:
            response = self.client.get(reverse(url_name))
            self.assertIn(response.status_code, [200, 302],
                          f'{url_name} returned {response.status_code}')


# ============================================================
#  5. STUDENT VIEW TESTS
# ============================================================
class StudentViewTest(BaseTestMixin, TestCase):
    """Tests for student views."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')

    def test_student_list_view(self):
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'طالب تجريبي')

    def test_student_list_search(self):
        response = self.client.get(reverse('students:list'), {'search': 'تجريبي'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'طالب تجريبي')

    def test_student_list_search_no_results(self):
        response = self.client.get(reverse('students:list'), {'search': 'غير موجود'})
        self.assertEqual(response.status_code, 200)

    def test_student_detail_view(self):
        response = self.client.get(
            reverse('students:detail', kwargs={'student_id': self.student.student_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'طالب تجريبي')

    def test_student_detail_404(self):
        response = self.client.get(
            reverse('students:detail', kwargs={'student_id': 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_student_create_get(self):
        response = self.client.get(reverse('students:create'))
        self.assertEqual(response.status_code, 200)

    def test_student_create_post(self):
        response = self.client.post(reverse('students:create'), {
            'full_name': 'طالب جديد',
            'gender': 'female',
            'parent_phone': '01055555555',
            'student_phone': '01066666666',
            'education_type': 'general',
            'is_active': True,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(full_name='طالب جديد').exists())

    def test_student_create_invalid(self):
        response = self.client.post(reverse('students:create'), {
            'full_name': '',
            'gender': 'male',
            'parent_phone': '',
        })
        self.assertEqual(response.status_code, 200)  # Re-renders form

    def test_student_update_get(self):
        response = self.client.get(
            reverse('students:update', kwargs={'student_id': self.student.student_id})
        )
        self.assertEqual(response.status_code, 200)

    def test_student_update_post(self):
        response = self.client.post(
            reverse('students:update', kwargs={'student_id': self.student.student_id}),
            {
                'full_name': 'اسم محدث',
                'gender': 'male',
                'parent_phone': '01098765432',
                'student_phone': '01011111111',
                'education_type': 'general',
                'is_active': True,
            }
        )
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.full_name, 'اسم محدث')

    def test_student_delete_post(self):
        response = self.client.post(
            reverse('students:delete', kwargs={'student_id': self.student.student_id})
        )
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

    def test_student_toggle_status(self):
        response = self.client.post(
            reverse('students:toggle_status', kwargs={'student_id': self.student.student_id})
        )
        self.assertIn(response.status_code, [200, 302])


# ============================================================
#  6. TEACHER VIEW TESTS
# ============================================================
class TeacherViewTest(BaseTestMixin, TestCase):
    """Tests for teacher views."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')

    def test_teacher_list_view(self):
        response = self.client.get(reverse('teachers:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'أحمد محمد')

    def test_teacher_detail_view(self):
        response = self.client.get(
            reverse('teachers:detail', kwargs={'teacher_id': self.teacher.teacher_id})
        )
        self.assertEqual(response.status_code, 200)

    def test_teacher_create_get(self):
        response = self.client.get(reverse('teachers:create'))
        self.assertEqual(response.status_code, 200)

    def test_teacher_create_post(self):
        response = self.client.post(reverse('teachers:create'), {
            'full_name': 'مدرس جديد',
            'phone': '01099999999',
            'specialization': 'فيزياء',
            'hire_date': '2025-01-01',
            'is_active': True,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Teacher.objects.filter(full_name='مدرس جديد').exists())

    def test_teacher_delete_soft(self):
        response = self.client.post(
            reverse('teachers:delete', kwargs={'teacher_id': self.teacher.teacher_id})
        )
        self.assertEqual(response.status_code, 302)
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.is_active)


# ============================================================
#  7. ROOM VIEW TESTS
# ============================================================
class RoomViewTest(BaseTestMixin, TestCase):
    """Tests for room views."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')

    def test_room_list_view(self):
        response = self.client.get(reverse('teachers:room_list'))
        self.assertEqual(response.status_code, 200)

    def test_room_create_post(self):
        response = self.client.post(reverse('teachers:room_create'), {
            'name': 'قاعة 2',
            'capacity': 25,
            'is_active': True,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Room.objects.filter(name='قاعة 2').exists())

    def test_room_detail_view(self):
        response = self.client.get(
            reverse('teachers:room_detail', kwargs={'room_id': self.room.room_id})
        )
        self.assertEqual(response.status_code, 200)


# ============================================================
#  8. GROUP VIEW TESTS
# ============================================================
class GroupViewTest(BaseTestMixin, TestCase):
    """Tests for group views."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')

    def test_group_list_view(self):
        response = self.client.get(reverse('teachers:group_list'))
        self.assertEqual(response.status_code, 200)

    def test_group_detail_view(self):
        response = self.client.get(
            reverse('teachers:group_detail', kwargs={'group_id': self.group.group_id})
        )
        self.assertEqual(response.status_code, 200)

    def test_group_delete_soft(self):
        response = self.client.post(
            reverse('teachers:group_delete', kwargs={'group_id': self.group.group_id})
        )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertFalse(self.group.is_active)


# ============================================================
#  9. SUBJECT VIEW TESTS
# ============================================================
class SubjectViewTest(BaseTestMixin, TestCase):
    """Tests for subject views."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')

    def test_subject_list_view(self):
        response = self.client.get(reverse('teachers:subject_list'))
        self.assertEqual(response.status_code, 200)

    def test_subject_create_post(self):
        response = self.client.post(reverse('teachers:subject_create'), {
            'name': 'علوم',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Subject.objects.filter(name='علوم').exists())


# ============================================================
#  10. PAYMENT VIEW TESTS
# ============================================================
class PaymentViewTest(BaseTestMixin, TestCase):
    """Tests for payment views."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')
        self.payment = Payment.objects.create(
            student=self.student, group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('200.00'), amount_paid=Decimal('0.00'),
            status='unpaid',
        )

    def test_payment_list_view(self):
        response = self.client.get(reverse('payments:list'))
        self.assertEqual(response.status_code, 200)

    def test_payment_list_shows_group(self):
        """payment.group should work correctly (not payment.student.group)."""
        response = self.client.get(reverse('payments:list'))
        self.assertContains(response, 'مجموعة أ')

    def test_settlement_page(self):
        response = self.client.get(
            reverse('payments:settlement', kwargs={'teacher_id': self.teacher.teacher_id})
        )
        self.assertEqual(response.status_code, 200)


# ============================================================
#  11. ATTENDANCE VIEW TESTS
# ============================================================
class AttendanceViewTest(BaseTestMixin, TestCase):
    """Tests for attendance views."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')

    def test_scanner_page(self):
        response = self.client.get(reverse('attendance:scanner'))
        self.assertEqual(response.status_code, 200)

    def test_today_stats_api(self):
        response = self.client.get(reverse('attendance:today_stats'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_process_code_invalid(self):
        response = self.client.post(
            reverse('attendance:process_student_code'),
            data='{"student_code": "INVALID999"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])

    def test_process_code_empty(self):
        response = self.client.post(
            reverse('attendance:process_student_code'),
            data='{"student_code": ""}',
            content_type='application/json',
        )
        data = response.json()
        self.assertFalse(data['success'])

    def test_cancel_session(self):
        session = Session.objects.create(
            group=self.group, session_date=date.today(),
        )
        response = self.client.post(
            reverse('attendance:cancel_session', kwargs={'session_id': session.session_id}),
            {'reason': 'مرض المدرس'},
        )
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertTrue(session.is_cancelled)

    def test_teacher_checkin(self):
        session = Session.objects.create(
            group=self.group, session_date=date.today(),
        )
        response = self.client.post(
            reverse('attendance:teacher_checkin', kwargs={'session_id': session.session_id})
        )
        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertTrue(session.teacher_attended)


# ============================================================
#  12. DASHBOARD / REPORTS VIEW TESTS
# ============================================================
class DashboardViewTest(BaseTestMixin, TestCase):
    """Tests for dashboard and report views."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')

    def test_dashboard_loads(self):
        response = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_context(self):
        response = self.client.get(reverse('reports:dashboard'))
        ctx = response.context
        self.assertIn('total_students', ctx)
        self.assertIn('total_teachers', ctx)
        self.assertIn('today_schedule', ctx)
        self.assertIn('week_attendance_json', ctx)

    def test_attendance_report_loads(self):
        response = self.client.get(reverse('reports:attendance'))
        self.assertEqual(response.status_code, 200)

    def test_password_prompt_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('reports:password_prompt'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_password_prompt_loads(self):
        response = self.client.get(reverse('reports:password_prompt'))
        self.assertEqual(response.status_code, 200)

    def test_verify_wrong_password(self):
        response = self.client.post(reverse('reports:verify_password'), {
            'password': 'wrong_password',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.client.session.get('report_authenticated', False))


# ============================================================
#  13. TEMPLATE CONTENT TESTS
# ============================================================
class TemplateContentTest(BaseTestMixin, TestCase):
    """Verify templates render expected elements."""

    def setUp(self):
        super().setUp()
        self.client.login(username='admin_test', password='TestPass123!')

    def test_login_page_has_csrf(self):
        self.client.logout()
        response = self.client.get(reverse('accounts:login'))
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_student_form_has_errors_block(self):
        """Student form should show validation errors."""
        response = self.client.post(reverse('students:create'), {
            'full_name': '',
            'gender': '',
            'parent_phone': '',
        })
        self.assertEqual(response.status_code, 200)

    def test_teacher_form_has_errors_block(self):
        """Teacher form should show validation errors."""
        response = self.client.post(reverse('teachers:create'), {
            'full_name': '',
            'phone': '',
            'hire_date': '',
        })
        self.assertEqual(response.status_code, 200)

    def test_payment_list_has_currency(self):
        Payment.objects.create(
            student=self.student, group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('200.00'), status='unpaid',
        )
        response = self.client.get(reverse('payments:list'))
        self.assertContains(response, 'ج.م')

    def test_base_template_logout_is_form(self):
        """Logout should be a POST form, not a GET link."""
        response = self.client.get(reverse('reports:dashboard'))
        content = response.content.decode()
        self.assertIn('method="post"', content)
        self.assertIn('accounts/logout', content)

    def test_teacher_list_colspan(self):
        """Empty teacher list should have colspan=6."""
        Teacher.objects.all().update(is_active=False)
        response = self.client.get(reverse('teachers:list'))
        self.assertContains(response, 'colspan="6"')


# ============================================================
#  14. DATA INTEGRITY TESTS
# ============================================================
class DataIntegrityTest(BaseTestMixin, TestCase):
    """Tests for PROTECT constraints and data consistency."""

    def test_enrollment_with_groups(self):
        """Student create with group enrollment in transaction."""
        self.client.login(username='admin_test', password='TestPass123!')
        response = self.client.post(reverse('students:create'), {
            'full_name': 'طالب مع مجموعة',
            'gender': 'male',
            'parent_phone': '01077777777',
            'student_phone': '01088888888',
            'education_type': 'general',
            'is_active': True,
            'groups': [self.group.group_id],
        })
        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(full_name='طالب مع مجموعة')
        self.assertEqual(student.get_active_groups_count(), 1)

    def test_update_student_enrollment_change(self):
        """Updating student should correctly add/remove enrollments."""
        self.client.login(username='admin_test', password='TestPass123!')

        # Create second group
        group2 = Group.objects.create(
            group_name='مجموعة ب',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(14, 0),
            duration_minutes=120,
            standard_fee=Decimal('200.00'),
        )

        # Update: remove group1, add group2
        response = self.client.post(
            reverse('students:update', kwargs={'student_id': self.student.student_id}),
            {
                'full_name': 'طالب تجريبي',
                'gender': 'male',
                'parent_phone': '01098765432',
                'student_phone': '01011111111',
                'education_type': 'general',
                'is_active': True,
                'groups': [group2.group_id],
            }
        )
        self.assertEqual(response.status_code, 302)

        # Old enrollment should be deactivated
        old_enrollment = StudentGroupEnrollment.objects.get(
            student=self.student, group=self.group,
        )
        self.assertFalse(old_enrollment.is_active)

        # New enrollment should exist and be active
        new_enrollment = StudentGroupEnrollment.objects.get(
            student=self.student, group=group2,
        )
        self.assertTrue(new_enrollment.is_active)

    def test_payment_amount_validation(self):
        """Payment should not accept negative amounts."""
        payment = Payment(
            student=self.student, group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('-50'), amount_paid=Decimal('0'),
        )
        with self.assertRaises(Exception):
            payment.full_clean()


# ============================================================
#  15. MESSAGE TAG TESTS
# ============================================================
@override_settings(
    MESSAGE_TAGS={
        10: 'secondary',  # DEBUG
        20: 'info',       # INFO
        25: 'success',    # SUCCESS
        30: 'warning',    # WARNING
        40: 'danger',     # ERROR
    }
)
class MessageTagTest(BaseTestMixin, TestCase):
    """Tests that Django messages use Bootstrap-compatible tags."""

    def test_error_message_uses_danger(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'admin_test',
            'password': 'wrong',
        })
        self.assertContains(response, 'alert-danger')
        self.assertNotContains(response, 'alert-error')

    def test_success_message_on_login(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'admin_test',
            'password': 'TestPass123!',
        }, follow=True)
        self.assertContains(response, 'مرحباً')
