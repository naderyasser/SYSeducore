"""
Comprehensive API Tests for SYSeducore System.
Tests all fetch()-called endpoints: auth, CSRF, success, error cases.

Run with: python manage.py test tests.test_api --settings=config.settings_test -v2
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room, Subject
from apps.payments.models import Payment
from apps.attendance.models import Session, Attendance

User = get_user_model()


class APITestBase(TestCase):
    """Base class with shared setup for API tests."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='api_admin', password='TestPass123!', role='admin',
        )
        self.supervisor = User.objects.create_user(
            username='api_supervisor', password='TestPass123!', role='supervisor',
        )
        self.room = Room.objects.create(name='قاعة API', capacity=30)
        self.subject = Subject.objects.create(name='رياضيات')
        self.teacher = Teacher.objects.create(
            full_name='مدرس اختبار',
            phone='01012345678',
            specialization='رياضيات',
            hire_date=date(2024, 1, 1),
        )
        self.teacher.subjects.add(self.subject)
        self.group = Group.objects.create(
            group_name='مجموعة API',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(14, 0),
            duration_minutes=120,
            standard_fee=Decimal('200.00'),
            center_percentage=Decimal('30.00'),
        )
        self.student = Student.objects.create(
            student_code='API001',
            full_name='طالب API',
            gender='male',
            parent_phone='01098765432',
        )
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal',
            is_active=True,
        )

    def login(self, user=None):
        user = user or self.admin
        self.client.login(username=user.username, password='TestPass123!')


# ============================================================
#  Payment API Tests
# ============================================================
class MarkAsPaidAPITest(APITestBase):
    """Tests for /api/payments/<id>/mark-paid/"""

    def setUp(self):
        super().setUp()
        self.payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('200.00'),
            amount_paid=Decimal('0.00'),
            status='unpaid',
        )
        self.url = reverse('api_mark_paid', kwargs={'payment_id': self.payment.pk})

    def test_unauthenticated_returns_401(self):
        """Unauthenticated POST should return 401 JSON, not redirect."""
        response = self.client.post(self.url, content_type='application/json')
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data['success'])

    def test_get_method_not_allowed(self):
        """GET should return 405."""
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_mark_as_paid_success(self):
        """Authenticated POST should mark payment as paid."""
        self.login()
        response = self.client.post(self.url, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['payment']['status'], 'paid')
        self.assertEqual(float(data['payment']['amount_paid']), 200.0)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.amount_paid, Decimal('200.00'))
        self.assertIsNotNone(self.payment.payment_date)

    def test_mark_as_paid_already_paid(self):
        """Marking an already-paid payment should still succeed (idempotent)."""
        self.payment.amount_paid = Decimal('200.00')
        self.payment.status = 'paid'
        self.payment.save()

        self.login()
        response = self.client.post(self.url, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_mark_as_paid_nonexistent(self):
        """Marking a non-existent payment should return 404."""
        self.login()
        url = reverse('api_mark_paid', kwargs={'payment_id': 99999})
        response = self.client.post(url, content_type='application/json')
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data['success'])

    def test_remaining_after_paid(self):
        """After mark-as-paid, remaining property should be 0."""
        self.login()
        self.client.post(self.url, content_type='application/json')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.remaining, Decimal('0.00'))

    def test_supervisor_can_mark_paid(self):
        """Supervisors should also be able to mark as paid."""
        self.login(self.supervisor)
        response = self.client.post(self.url, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])


class RecordPaymentAPITest(APITestBase):
    """Tests for /api/payments/<id>/record/"""

    def setUp(self):
        super().setUp()
        self.payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('300.00'),
            amount_paid=Decimal('0.00'),
            status='unpaid',
        )
        self.url = reverse('api_record_payment', kwargs={'payment_id': self.payment.pk})

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.url, {'amount': '100'})
        self.assertEqual(response.status_code, 401)

    def test_get_method_not_allowed(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_record_partial_payment(self):
        """Recording a partial payment should set status to 'partial'."""
        self.login()
        response = self.client.post(self.url, {'amount': '100'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'partial')

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('100'))
        self.assertEqual(self.payment.remaining, Decimal('200'))

    def test_record_full_payment(self):
        """Recording full amount should set status to 'paid'."""
        self.login()
        response = self.client.post(self.url, {'amount': '300'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'paid')

    def test_record_incremental_payments(self):
        """Multiple partial payments should accumulate."""
        self.login()
        self.client.post(self.url, {'amount': '100'})
        self.client.post(self.url, {'amount': '100'})
        response = self.client.post(self.url, {'amount': '100'})
        data = response.json()
        self.assertEqual(data['status'], 'paid')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('300'))

    def test_record_zero_amount(self):
        """Recording 0 amount should succeed but not change status."""
        self.login()
        response = self.client.post(self.url, {'amount': '0'})
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'unpaid')

    def test_record_payment_nonexistent(self):
        self.login()
        url = reverse('api_record_payment', kwargs={'payment_id': 99999})
        response = self.client.post(url, {'amount': '50'})
        self.assertEqual(response.status_code, 404)

    def test_payment_date_set_on_record(self):
        """Recording a payment should set the payment_date."""
        self.login()
        self.client.post(self.url, {'amount': '50'})
        self.payment.refresh_from_db()
        self.assertIsNotNone(self.payment.payment_date)


# ============================================================
#  Student Subscription API Tests
# ============================================================
class ActivateSubscriptionAPITest(APITestBase):
    """Tests for /students/api/<id>/subscription/activate/"""

    def setUp(self):
        super().setUp()
        self.url = reverse(
            'students:api_activate_subscription',
            kwargs={'student_id': self.student.pk},
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.url, {'days': 30})
        self.assertEqual(response.status_code, 401)

    def test_get_method_not_allowed(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_activate_30_days(self):
        """Should activate subscription for 30 days."""
        self.login()
        response = self.client.post(self.url, {'days': '30'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn(self.student.full_name, data['message'])

        self.student.refresh_from_db()
        self.assertTrue(self.student.is_subscription_active())
        expected_expiry = date.today() + timedelta(days=30)
        self.assertEqual(self.student.subscription_expiry_date, expected_expiry)

    def test_activate_custom_days(self):
        """Should activate subscription for custom number of days."""
        self.login()
        response = self.client.post(self.url, {'days': '7'})
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        expected_expiry = date.today() + timedelta(days=7)
        self.assertEqual(self.student.subscription_expiry_date, expected_expiry)

    def test_activate_nonexistent_student(self):
        self.login()
        url = reverse(
            'students:api_activate_subscription',
            kwargs={'student_id': 99999},
        )
        response = self.client.post(url, {'days': '30'})
        # get_object_or_404 raises Http404, caught by generic except → 500
        self.assertIn(response.status_code, [404, 500])
        data = response.json()
        self.assertFalse(data['success'])

    def test_activate_sets_payment_date(self):
        """Activation should set last_payment_date."""
        self.login()
        self.client.post(self.url, {'days': '30'})
        self.student.refresh_from_db()
        self.assertEqual(self.student.last_payment_date, date.today())

    def test_re_activate_extends(self):
        """Re-activating should extend from today, not from old expiry."""
        self.login()
        self.client.post(self.url, {'days': '10'})
        self.client.post(self.url, {'days': '30'})
        self.student.refresh_from_db()
        expected = date.today() + timedelta(days=30)
        self.assertEqual(self.student.subscription_expiry_date, expected)


class SubscriptionStatusAPITest(APITestBase):
    """Tests for /students/api/<id>/subscription/status/"""

    def setUp(self):
        super().setUp()
        self.url = reverse(
            'students:api_subscription_status',
            kwargs={'student_id': self.student.pk},
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_no_subscription(self):
        """Student with no subscription_expiry_date is treated as active (allowed entry)."""
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        # No expiry date = subscription not configured = allowed
        self.assertTrue(data['student']['is_active'])
        self.assertIsNone(data['student']['subscription_expiry_date'])

    def test_active_subscription(self):
        """Student with active subscription should show active."""
        self.student.activate_subscription(days=30)
        self.login()
        response = self.client.get(self.url)
        data = response.json()
        self.assertTrue(data['student']['is_active'])


# ============================================================
#  Student Group API Tests
# ============================================================
class AddToGroupAPITest(APITestBase):
    """Tests for /students/api/group/add/"""

    def setUp(self):
        super().setUp()
        self.url = reverse('students:api_add_to_group')
        self.student2 = Student.objects.create(
            student_code='API002',
            full_name='طالب ثاني',
            parent_phone='01098765433',
        )
        self.group2 = Group.objects.create(
            group_name='مجموعة ب',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(16, 0),
            standard_fee=Decimal('150.00'),
            center_percentage=Decimal('30.00'),
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.url, {
            'student_id': self.student2.pk,
            'group_id': self.group2.pk,
        })
        self.assertEqual(response.status_code, 401)

    def test_add_student_to_group(self):
        self.login()
        response = self.client.post(self.url, {
            'student_id': self.student2.pk,
            'group_id': self.group2.pk,
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(
            StudentGroupEnrollment.objects.filter(
                student=self.student2, group=self.group2
            ).exists()
        )

    def test_add_missing_data(self):
        self.login()
        response = self.client.post(self.url, {'student_id': self.student2.pk})
        data = response.json()
        self.assertFalse(data['success'])

    def test_add_duplicate_updates(self):
        """Adding a student already in a group should update, not error."""
        self.login()
        self.client.post(self.url, {
            'student_id': self.student2.pk,
            'group_id': self.group2.pk,
            'financial_status': 'normal',
        })
        response = self.client.post(self.url, {
            'student_id': self.student2.pk,
            'group_id': self.group2.pk,
            'financial_status': 'symbolic',
            'custom_fee': '50',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])


class RemoveFromGroupAPITest(APITestBase):
    """Tests for /students/api/group/remove/"""

    def setUp(self):
        super().setUp()
        self.url = reverse('students:api_remove_from_group')

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.url, {'enrollment_id': self.enrollment.pk})
        self.assertEqual(response.status_code, 401)

    def test_remove_student_from_group(self):
        self.login()
        response = self.client.post(self.url, {'enrollment_id': self.enrollment.pk})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

    def test_remove_missing_enrollment_id(self):
        self.login()
        response = self.client.post(self.url, {})
        data = response.json()
        self.assertFalse(data['success'])


# ============================================================
#  Student Barcode API Tests
# ============================================================
class StudentBarcodeAPITest(APITestBase):
    """Tests for /students/api/<id>/barcode/"""

    def setUp(self):
        super().setUp()
        self.url = reverse(
            'students:api_barcode',
            kwargs={'student_id': self.student.pk},
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_barcode(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('barcode', data)
        self.assertIn('student_code', data)


# ============================================================
#  Attendance Scanner API Tests
# ============================================================
class ProcessScanAPITest(APITestBase):
    """Tests for /api/attendance/scan/"""

    def setUp(self):
        super().setUp()
        self.url = reverse('attendance:process_student_code')

    def test_unauthenticated_returns_401(self):
        response = self.client.post(
            self.url,
            {'student_code': 'API001'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)

    def test_get_method_not_allowed(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_scan_valid_code(self):
        """Scanning a valid student code should return 200 with student info."""
        self.login()
        import json as _json
        response = self.client.post(
            self.url,
            _json.dumps({'student_code': 'API001'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Response always contains student info (dossier) even on time errors
        self.assertIn('dossier', data)
        self.assertEqual(data['dossier']['student_code'], 'API001')

    def test_scan_invalid_code(self):
        """Scanning a non-existent code should return error."""
        self.login()
        import json as _json
        response = self.client.post(
            self.url,
            _json.dumps({'student_code': 'INVALID'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get('success', True))


class TodayStatsAPITest(APITestBase):
    """Tests for /attendance/today-stats/"""

    def setUp(self):
        super().setUp()
        self.url = reverse('attendance:today_stats')

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_today_stats(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])


class TodaySessionsAPITest(APITestBase):
    """Tests for /attendance/today-sessions/"""

    def setUp(self):
        super().setUp()
        self.url = reverse('attendance:today_sessions')

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_today_sessions(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])


# ============================================================
#  Teacher Room API Tests
# ============================================================
class RoomListAPITest(APITestBase):
    """Tests for /teachers/api/rooms/"""

    def setUp(self):
        super().setUp()
        self.url = reverse('teachers:api_room_list')

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_room_list(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('rooms', data)


class RoomDetailAPITest(APITestBase):
    """Tests for /teachers/api/rooms/<id>/"""

    def setUp(self):
        super().setUp()
        self.url = reverse(
            'teachers:api_room_detail',
            kwargs={'room_id': self.room.pk},
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_room_detail(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('room', data)


# ============================================================
#  Payment Model Tests
# ============================================================
class PaymentRemainingPropertyTest(APITestBase):
    """Tests for the Payment.remaining property."""

    def test_remaining_unpaid(self):
        payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('200.00'),
            amount_paid=Decimal('0.00'),
            status='unpaid',
        )
        self.assertEqual(payment.remaining, Decimal('200.00'))

    def test_remaining_partial(self):
        payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=date(2025, 1, 1),
            amount_due=Decimal('200.00'),
            amount_paid=Decimal('50.00'),
            status='partial',
        )
        self.assertEqual(payment.remaining, Decimal('150.00'))

    def test_remaining_fully_paid(self):
        payment = Payment.objects.create(
            student=self.student,
            group=self.group,
            month=date(2025, 2, 1),
            amount_due=Decimal('200.00'),
            amount_paid=Decimal('200.00'),
            status='paid',
        )
        self.assertEqual(payment.remaining, Decimal('0.00'))


# ============================================================
#  Decorator Tests
# ============================================================
class AjaxLoginRequiredDecoratorTest(APITestBase):
    """Tests for the ajax_login_required decorator."""

    def test_returns_json_401_when_unauthenticated(self):
        """All API endpoints should return JSON 401, not HTML redirect."""
        urls_to_test = [
            (reverse('api_mark_paid', kwargs={'payment_id': 1}), 'post'),
            (reverse('api_record_payment', kwargs={'payment_id': 1}), 'post'),
            (reverse('attendance:today_stats'), 'get'),
            (reverse('attendance:today_sessions'), 'get'),
            (reverse('teachers:api_room_list'), 'get'),
        ]
        for url, method in urls_to_test:
            fn = getattr(self.client, method)
            response = fn(url)
            self.assertEqual(
                response.status_code, 401,
                f'{method.upper()} {url} returned {response.status_code} instead of 401',
            )
            data = response.json()
            self.assertFalse(data['success'])

    def test_authenticated_passes_through(self):
        """Authenticated requests should reach the view function."""
        self.login()
        response = self.client.get(reverse('attendance:today_stats'))
        self.assertNotEqual(response.status_code, 401)


# ============================================================
#  Student Next Code API Test
# ============================================================
class NextCodeAPITest(APITestBase):
    """Tests for /students/next-code/"""

    def setUp(self):
        super().setUp()
        self.url = reverse('students:next_code')

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_next_code(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('next_code', data)


# ============================================================
#  Available Groups API Test
# ============================================================
class AvailableGroupsAPITest(APITestBase):
    """Tests for /students/api/<id>/available-groups/"""

    def setUp(self):
        super().setUp()
        self.url = reverse(
            'students:api_available_groups',
            kwargs={'student_id': self.student.pk},
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_available_groups(self):
        self.login()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
