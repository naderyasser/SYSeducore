"""
Tests for Payment Service
"""

from datetime import date, time
from decimal import Decimal

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.teachers.models import Teacher, Group, Room
from tests.factories import create_group_with_schedule
from apps.students.models import Student, StudentGroupEnrollment
from apps.attendance.models import ActivityLog, Session, Attendance
from apps.payments.admin import PaymentAdmin
from apps.payments.models import Payment, PaymentAmountError, PaymentTransaction
from apps.payments.services import SettlementService
from apps.payments.views import _ensure_monthly_payments

User = get_user_model()


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
        self.group = create_group_with_schedule(
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
        self.assertTrue(result.get('success'))
        self.assertIn('total_revenue', result['data'])
        self.assertIn('teacher_share', result['data'])

    def test_calculate_group_revenue(self):
        """Test group revenue calculation"""
        now = timezone.now().date()
        result = self.service.calculate_group_revenue(
            self.group.pk, now.year, now.month,
        )
        self.assertIn('revenue', result)

    def test_calculate_settlement_with_different_center_percentage(self):
        """Test settlement with different center percentage"""
        self.group.center_percentage = Decimal('40.00')
        self.group.save()

        now = timezone.now().date()
        result = self.service.calculate_teacher_settlement(
            self.teacher.pk, now.year, now.month,
        )
        self.assertIn('teacher_share', result['data'])

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

        # Use a date that doesn't conflict with setUp sessions
        session = Session.objects.create(
            group=self.group,
            session_date=timezone.now().date() + timedelta(days=1),
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
        self.assertTrue(result.get('success'))
        self.assertIn('total_revenue', result['data'])


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
        self.group = create_group_with_schedule(
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

    def test_zero_fee_payment_is_flagged_exempt_on_save(self):
        """
        Every creation path — not just ``_ensure_monthly_payments`` — must
        yield ``is_exempt=True`` for a zero-fee row, or it is counted as a
        real (100%) collection in the payments-page stats.
        """
        zero_fee = Payment.objects.create(
            student=self.student, group=self.group,
            month=date(2026, 6, 1), amount_due=Decimal('0.00'),
            amount_paid=Decimal('0.00'), status='paid',
        )
        self.assertTrue(zero_fee.is_exempt)
        zero_fee.refresh_from_db()
        self.assertTrue(zero_fee.is_exempt)


# ============================================================
#  Payment ledger (QUAL-06) — audit trail, over/under-payment
# ============================================================
class LedgerTestBase(TestCase):
    """Shared fixture: one student, one group, one 300 ج.م payment."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='ledger_admin', password='TestPass123!', role='admin',
        )
        self.supervisor = User.objects.create_user(
            username='ledger_supervisor', password='TestPass123!', role='supervisor',
        )
        self.teacher_user = User.objects.create_user(
            username='ledger_teacher_user', password='TestPass123!', role='teacher',
        )
        self.room = Room.objects.create(name='قاعة السجل', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس السجل', phone='01234500000',
            specialization='رياضيات', hire_date=timezone.localdate(),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة السجل', teacher=self.teacher, room=self.room,
            schedule_day='Tuesday', schedule_time=time(15, 0),
            standard_fee=Decimal('300.00'), center_percentage=Decimal('30.00'),
        )
        self.student = Student.objects.create(
            student_code='LDG001', full_name='طالب السجل',
            parent_phone='01234500001',
        )
        self.enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group, financial_status='normal',
        )
        self.month = timezone.localdate().replace(day=1)
        self.payment = Payment.objects.create(
            student=self.student, group=self.group, month=self.month,
            amount_due=Decimal('300.00'), amount_paid=Decimal('0.00'),
            status='unpaid',
        )


class PaymentLedgerTest(LedgerTestBase):

    def test_record_transaction_writes_receipt_and_reconciles(self):
        txn = self.payment.record_transaction(
            '120', user=self.supervisor, note='دفعة أولى',
        )
        self.assertIsNotNone(txn)
        self.assertEqual(txn.amount, Decimal('120.00'))
        self.assertEqual(txn.created_by, self.supervisor)
        self.assertEqual(txn.kind, PaymentTransaction.KIND_PAYMENT)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('120.00'))
        self.assertEqual(self.payment.status, 'partial')
        self.assertIsNotNone(self.payment.payment_date)
        self.assertEqual(self.payment.ledger_total(), Decimal('120.00'))

    def test_negative_amount_is_rejected(self):
        self.payment.record_transaction('200', user=self.supervisor)
        with self.assertRaises(PaymentAmountError):
            self.payment.record_transaction('-50', user=self.supervisor)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('200.00'))
        self.assertEqual(self.payment.transactions.count(), 1)

    def test_over_payment_is_rejected(self):
        self.payment.record_transaction('250', user=self.supervisor)
        with self.assertRaises(PaymentAmountError):
            self.payment.record_transaction('100', user=self.supervisor)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('250.00'))

    def test_invalid_amount_raises_arabic_error(self):
        with self.assertRaises(PaymentAmountError) as ctx:
            self.payment.record_transaction('abc', user=self.supervisor)
        self.assertIn('غير صالحة', str(ctx.exception))

    def test_huge_exponent_amount_raises_arabic_error_not_500(self):
        """
        A value whose ``quantize()`` overflows the Decimal context precision
        must surface as the same Arabic ``PaymentAmountError`` as any other
        bad amount, not as an uncaught ``InvalidOperation``.
        """
        with self.assertRaises(PaymentAmountError) as ctx:
            self.payment.record_transaction('1e30', user=self.supervisor)
        self.assertIn('غير صالحة', str(ctx.exception))

    def test_zero_amount_is_a_noop(self):
        self.assertIsNone(self.payment.record_transaction('0', user=self.supervisor))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'unpaid')
        self.assertEqual(self.payment.transactions.count(), 0)

    def test_settle_full_is_idempotent(self):
        self.payment.settle_full(user=self.supervisor)
        self.payment.settle_full(user=self.supervisor)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('300.00'))
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.transactions.count(), 1)

    def test_legacy_amount_paid_becomes_an_opening_balance(self):
        """A balance written outside the ledger is preserved, not erased."""
        Payment.objects.filter(pk=self.payment.pk).update(amount_paid=Decimal('100.00'))
        self.payment.refresh_from_db()

        self.payment.record_transaction('50', user=self.supervisor)
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.amount_paid, Decimal('150.00'))
        kinds = set(self.payment.transactions.values_list('kind', flat=True))
        self.assertEqual(kinds, {PaymentTransaction.KIND_OPENING,
                                 PaymentTransaction.KIND_PAYMENT})

    def test_reverse_all_records_the_reversal(self):
        self.payment.settle_full(user=self.supervisor)
        self.payment.reverse_all(user=self.admin, note='تصفير')
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.amount_paid, Decimal('0.00'))
        self.assertEqual(self.payment.status, 'unpaid')
        self.assertIsNone(self.payment.payment_date)
        self.assertEqual(self.payment.transactions.count(), 2)
        self.assertEqual(self.payment.ledger_total(), Decimal('0.00'))

    def test_exempt_row_stays_paid_but_flagged(self):
        exempt = Payment.objects.create(
            student=self.student, group=self.group,
            month=date(2020, 5, 1), amount_due=Decimal('0'),
            amount_paid=Decimal('0'), status='paid', is_exempt=True,
        )
        exempt.reconcile()
        self.assertEqual(exempt.status, 'paid')
        self.assertTrue(exempt.is_exempt)


class PaymentAPIPermissionTest(LedgerTestBase):
    """AUTH-01 — money endpoints are supervisor+ only."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.mark_url = reverse('api_mark_paid', kwargs={'payment_id': self.payment.pk})
        self.record_url = reverse('api_record_payment', kwargs={'payment_id': self.payment.pk})

    def test_teacher_cannot_mark_as_paid(self):
        self.client.login(username='ledger_teacher_user', password='TestPass123!')
        response = self.client.post(self.mark_url)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('0.00'))

    def test_teacher_cannot_record_payment(self):
        self.client.login(username='ledger_teacher_user', password='TestPass123!')
        response = self.client.post(self.record_url, {'amount': '100'})
        self.assertEqual(response.status_code, 403)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('0.00'))

    def test_supervisor_can_record_payment(self):
        self.client.login(username='ledger_supervisor', password='TestPass123!')
        response = self.client.post(self.record_url, {'amount': '100'})
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('100.00'))

    def test_api_rejects_negative_amount(self):
        self.client.login(username='ledger_supervisor', password='TestPass123!')
        response = self.client.post(self.record_url, {'amount': '-100'})
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body['success'])
        self.assertIn('سالب', body['message'])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('0.00'))

    def test_api_rejects_over_payment(self):
        self.client.login(username='ledger_supervisor', password='TestPass123!')
        response = self.client.post(self.record_url, {'amount': '5000'})
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('0.00'))
        self.assertEqual(self.payment.transactions.count(), 0)

    def test_api_records_who_took_the_money(self):
        self.client.login(username='ledger_supervisor', password='TestPass123!')
        self.client.post(self.mark_url)
        txn = self.payment.transactions.get()
        self.assertEqual(txn.created_by, self.supervisor)
        self.assertTrue(
            ActivityLog.objects.filter(
                target_model='Payment', target_id=self.payment.pk,
            ).exists()
        )

    def test_replaying_mark_as_paid_does_not_undo_deactivation(self):
        """
        A payment already settled must not be re-activated by a replayed
        mark-paid POST — ``settle_full`` returns ``None`` (no ledger row),
        so the student's deliberate deactivation must survive.
        """
        self.client.login(username='ledger_supervisor', password='TestPass123!')
        self.client.post(self.mark_url)
        self.assertEqual(self.payment.transactions.count(), 1)

        self.student.is_active = False
        self.student.subscription_expiry_date = date(2020, 1, 1)
        self.student.save(update_fields=['is_active', 'subscription_expiry_date'])

        response = self.client.post(self.mark_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.payment.transactions.count(), 1)

        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertEqual(self.student.subscription_expiry_date, date(2020, 1, 1))

    def test_settlement_page_is_admin_only(self):
        url = reverse('payments:settlement', kwargs={'teacher_id': self.teacher.pk})
        self.client.login(username='ledger_teacher_user', password='TestPass123!')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.login(username='ledger_supervisor', password='TestPass123!')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.login(username='ledger_admin', password='TestPass123!')
        self.assertEqual(self.client.get(url).status_code, 200)


class ActivateStudentForPaymentTest(LedgerTestBase):
    """DATA-16 — never enroll a student who was never enrolled."""

    def test_missing_enrollment_is_not_created(self):
        from apps.payments.api_views import _activate_student_for_payment

        other_group = create_group_with_schedule(
            group_name='مجموعة أخرى', teacher=self.teacher, room=self.room,
            schedule_day='Wednesday', schedule_time=time(17, 0),
            standard_fee=Decimal('200.00'), center_percentage=Decimal('30.00'),
        )
        payment = Payment.objects.create(
            student=self.student, group=other_group, month=self.month,
            amount_due=Decimal('200.00'), status='unpaid',
        )

        _activate_student_for_payment(payment, user=self.supervisor)

        self.assertFalse(
            StudentGroupEnrollment.objects.filter(
                student=self.student, group=other_group,
            ).exists()
        )

    def test_existing_inactive_enrollment_is_reactivated(self):
        from apps.payments.api_views import _activate_student_for_payment

        self.enrollment.is_active = False
        self.enrollment.save(update_fields=['is_active'])

        _activate_student_for_payment(self.payment, user=self.supervisor)

        self.enrollment.refresh_from_db()
        self.assertTrue(self.enrollment.is_active)


class MonthlyGenerationTest(LedgerTestBase):
    """DATA-14 / DATA-15 — generation is current-month only, exempt is flagged."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.login(username='ledger_admin', password='TestPass123!')

    def test_browsing_an_old_month_creates_nothing(self):
        before = Payment.objects.count()
        response = self.client.get(reverse('payments:list'), {'month': '2020-01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.filter(month=date(2020, 1, 1)).count(), 0)
        self.assertEqual(Payment.objects.count(), before)

    def test_current_month_is_generated(self):
        second = Student.objects.create(
            student_code='LDG002', full_name='طالب ثانٍ',
            parent_phone='01234500002',
        )
        StudentGroupEnrollment.objects.create(
            student=second, group=self.group, financial_status='normal',
        )
        self.client.get(reverse('payments:list'))
        self.assertTrue(
            Payment.objects.filter(student=second, month=self.month).exists()
        )

    def test_exempt_rows_are_flagged_and_excluded_from_collection(self):
        exempt_student = Student.objects.create(
            student_code='LDG003', full_name='طالب معفى',
            parent_phone='01234500003',
        )
        StudentGroupEnrollment.objects.create(
            student=exempt_student, group=self.group, financial_status='exempt',
        )
        _ensure_monthly_payments(self.month)

        row = Payment.objects.get(student=exempt_student, month=self.month)
        self.assertTrue(row.is_exempt)
        self.assertEqual(row.amount_due, Decimal('0'))

        response = self.client.get(reverse('payments:list'))
        stats = response.context['stats']
        self.assertEqual(stats['exempt'], 1)
        # The exempt row must not inflate the "paid" count.
        self.assertEqual(stats['paid'], 0)

    def test_generation_skips_soft_deleted_students(self):
        gone = Student.objects.create(
            student_code='LDG004', full_name='طالب محذوف',
            parent_phone='01234500004',
        )
        StudentGroupEnrollment.objects.create(
            student=gone, group=self.group, financial_status='normal',
        )
        gone.soft_delete()

        _ensure_monthly_payments(self.month)
        self.assertFalse(
            Payment.objects.filter(student=gone, month=self.month).exists()
        )

    def test_generation_skips_deactivated_group(self):
        """A closed group (is_active=False) must stop generating new charges,
        even though its enrollments stay active."""
        third = Student.objects.create(
            student_code='LDG005', full_name='طالب مجموعة مغلقة',
            parent_phone='01234500005',
        )
        StudentGroupEnrollment.objects.create(
            student=third, group=self.group, financial_status='normal',
        )
        self.group.is_active = False
        self.group.save(update_fields=['is_active'])

        _ensure_monthly_payments(self.month)
        self.assertFalse(
            Payment.objects.filter(student=third, month=self.month).exists()
        )


class PaymentListVisibilityTest(LedgerTestBase):
    """payment_list is supervisor+ and must not show soft-deleted students."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_teacher_role_is_forbidden(self):
        self.client.login(username='ledger_teacher_user', password='TestPass123!')
        response = self.client.get(reverse('payments:list'))
        self.assertEqual(response.status_code, 403)

    def test_supervisor_role_is_allowed(self):
        self.client.login(username='ledger_supervisor', password='TestPass123!')
        response = self.client.get(reverse('payments:list'))
        self.assertEqual(response.status_code, 200)

    def test_soft_deleted_student_is_excluded_from_list_and_stats(self):
        self.student.soft_delete()

        self.client.login(username='ledger_supervisor', password='TestPass123!')
        response = self.client.get(reverse('payments:list'))

        self.assertNotIn(
            self.payment.pk,
            [p.pk for p in response.context['payments']],
        )
        stats = response.context['stats']
        self.assertEqual(stats['billable_total'], 0)
        self.assertEqual(stats['unpaid'], 0)


class SettlementInactiveGroupTest(LedgerTestBase):
    """DATA-23 — a group closed mid-month keeps its revenue."""

    def test_inactive_group_revenue_still_counted(self):
        self.payment.settle_full(user=self.supervisor)
        self.group.is_active = False
        self.group.save(update_fields=['is_active'])

        result = SettlementService.calculate_teacher_settlement(
            self.teacher.pk, self.month.year, self.month.month,
        )
        self.assertEqual(result['data']['total_revenue'], 300.0)


class PaymentAdminActionTest(LedgerTestBase):
    """QUAL-05 — every admin bulk action is audited."""

    def _request(self):
        request = RequestFactory().post('/admin/payments/payment/')
        request.user = self.admin
        setattr(request, 'session', 'session')
        setattr(request, '_messages', FallbackStorage(request))
        return request

    def test_clear_payments_is_logged_and_reversed(self):
        self.payment.settle_full(user=self.supervisor)
        model_admin = PaymentAdmin(Payment, django_admin.site)
        model_admin.clear_payments(
            self._request(), Payment.objects.filter(pk=self.payment.pk),
        )

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('0.00'))
        self.assertEqual(self.payment.status, 'unpaid')
        self.assertTrue(
            ActivityLog.objects.filter(
                user=self.admin, target_model='Payment',
            ).exists()
        )
        # The reversal itself is in the ledger.
        self.assertTrue(
            self.payment.transactions.filter(
                kind=PaymentTransaction.KIND_REVERSAL,
            ).exists()
        )

    def test_mark_paid_action_is_logged(self):
        model_admin = PaymentAdmin(Payment, django_admin.site)
        model_admin.mark_paid(
            self._request(), Payment.objects.filter(pk=self.payment.pk),
        )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.amount_paid, Decimal('300.00'))
        self.assertTrue(ActivityLog.objects.filter(user=self.admin).exists())

    def test_amount_paid_is_not_list_editable(self):
        model_admin = PaymentAdmin(Payment, django_admin.site)
        self.assertNotIn('amount_paid', getattr(model_admin, 'list_editable', ()))
        self.assertNotIn('status', getattr(model_admin, 'list_editable', ()))


class LedgerBackfillMigrationTest(LedgerTestBase):
    """Migration 0006 must not lose money that predates the ledger."""

    def test_backfill_creates_opening_balances_and_flags_exempt(self):
        from importlib import import_module
        from django.apps import apps as global_apps

        Payment.objects.filter(pk=self.payment.pk).update(amount_paid=Decimal('200.00'))
        zero_fee = Payment.objects.create(
            student=self.student, group=self.group, month=date(2021, 3, 1),
            amount_due=Decimal('0'), amount_paid=Decimal('0'), status='paid',
        )

        migration = import_module('apps.payments.migrations.0006_backfill_payment_ledger')
        migration.backfill(global_apps, None)

        self.payment.refresh_from_db()
        zero_fee.refresh_from_db()

        opening = self.payment.transactions.get()
        self.assertEqual(opening.amount, Decimal('200.00'))
        self.assertEqual(opening.kind, PaymentTransaction.KIND_OPENING)
        self.assertTrue(zero_fee.is_exempt)

        # Idempotent: a second run must not double the balance.
        migration.backfill(global_apps, None)
        self.assertEqual(self.payment.transactions.count(), 1)
