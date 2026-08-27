"""
Unit Tests for Student App - Educore V2
اختبارات شاملة للنظام الجديد
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from .models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room
from tests.factories import create_group_with_schedule


class StudentModelTest(TestCase):
    """
    Unit Tests للـ Student Model
    اختبار التغيير من barcode إلى student_code
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.student_data = {
            'student_code': '1001',
            'full_name': 'أحمد محمد',
            'parent_phone': '+201234567890'
        }

    def test_create_student_with_student_code(self):
        """اختبار: إنشاء طالب بـ student_code"""
        student = Student.objects.create(**self.student_data)

        self.assertEqual(student.student_code, '1001')
        self.assertEqual(student.full_name, 'أحمد محمد')
        self.assertTrue(student.is_active)

    def test_student_code_is_unique(self):
        """اختبار: student_code يجب أن يكون فريداً"""
        Student.objects.create(**self.student_data)

        # محاولة إنشاء طالب آخر بنفس الكود
        with self.assertRaises(IntegrityError):
            Student.objects.create(**self.student_data)

    def test_student_code_max_length(self):
        """اختبار: student_code الحد الأقصى 10 أحرف"""
        student = Student.objects.create(
            student_code='1234567890',  # 10 أحرف - OK
            full_name='Test Student',
            parent_phone='+201234567890'
        )
        self.assertEqual(len(student.student_code), 10)

    def test_student_str_representation(self):
        """اختبار: __str__ يرجع الاسم الكامل"""
        student = Student.objects.create(**self.student_data)
        self.assertEqual(str(student), 'أحمد محمد')


class StudentGroupEnrollmentTest(TestCase):
    """
    Unit Tests لنموذج تسجيل الطالب في المجموعة
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        # إنشاء مدرس
        self.teacher = Teacher.objects.create(
            full_name='محمد علي',
            email='teacher@test.com',
            phone='+201234567890',
            specialization='رياضيات',
            hire_date='2020-01-01'
        )

        # إنشاء قاعة
        self.room = Room.objects.create(
            name='قاعة A',
            capacity=30
        )

        # إنشاء مجموعة
        self.group = create_group_with_schedule(
            group_name='مجموعة السبت',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        # إنشاء طالب
        self.student = Student.objects.create(
            student_code='1001',
            full_name='أحمد محمد',
            parent_phone='+201234567890'
        )

    def test_create_enrollment_normal_status(self):
        """اختبار: إنشاء تسجيل بحالة مالية عادية"""
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

        self.assertEqual(enrollment.financial_status, 'normal')
        self.assertIsNone(enrollment.custom_fee)
        self.assertTrue(enrollment.is_active)

    def test_create_enrollment_exempt_status(self):
        """اختبار: إنشاء تسجيل بحالة إعفاء كامل"""
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='exempt'
        )

        self.assertEqual(enrollment.financial_status, 'exempt')
        # الطالب المعفي: المصروفات = 0
        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, 0)

    def test_create_enrollment_symbolic_status(self):
        """اختبار: إنشاء تسجيل بحالة مبلغ رمزي"""
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='symbolic',
            custom_fee=50.00
        )

        self.assertEqual(enrollment.financial_status, 'symbolic')
        self.assertEqual(enrollment.custom_fee, 50.00)

        # المصروفات = المبلغ الرمزي
        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, 50.00)

    def test_unique_student_group_constraint(self):
        """اختبار: لا يمكن تسجيل طالب في نفس المجموعة مرتين"""
        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group
        )

        # محاولة تسجيل مرة ثانية
        with self.assertRaises(IntegrityError):
            StudentGroupEnrollment.objects.create(
                student=self.student,
                group=self.group
            )

    def test_get_monthly_fee_for_group_normal(self):
        """اختبار: حساب المصروفات الشهرية - حالة عادية"""
        StudentGroupEnrollment.objects.create(
            student=self.student,
            group=self.group,
            financial_status='normal'
        )

        fee = self.student.get_monthly_fee_for_group(self.group)
        self.assertEqual(fee, 200.00)  # السعر القياسي


# ============================================================
#  Regression tests for the 2026-07-24 full-system audit
#  (AUTH-02/05/06, BUG-07/08, DATA-01/02/06/08/09/10/12/22/28,
#   PERF-01/02, QUAL-01/02)
# ============================================================
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.attendance.models import ActivityLog
from apps.payments.models import Payment
from .forms import StudentForm, StudentQuickForm
from .utils import normalize_financial_status, normalize_phone, parse_money

User = get_user_model()


class AuditBaseTest(TestCase):
    """Shared fixtures for the audit regression tests."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='audit_admin', password='TestPass123!', role='admin',
        )
        self.supervisor = User.objects.create_user(
            username='audit_supervisor', password='TestPass123!', role='supervisor',
        )
        self.teacher_user = User.objects.create_user(
            username='audit_teacher', password='TestPass123!', role='teacher',
        )
        self.room = Room.objects.create(name='قاعة التدقيق', capacity=30)
        self.teacher = Teacher.objects.create(
            full_name='مدرس التدقيق',
            phone='01012345678',
            specialization='رياضيات',
            hire_date=date(2024, 1, 1),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة أ',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(14, 0),
            standard_fee=Decimal('200.00'),
        )
        self.group2 = create_group_with_schedule(
            group_name='مجموعة ب',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(16, 0),
            standard_fee=Decimal('300.00'),
        )
        self.student = Student.objects.create(
            student_code='AUD001',
            full_name='طالب التدقيق',
            gender='male',
            parent_phone='01098765432',
            student_phone='01011111111',
        )

    def login(self, user=None):
        user = user or self.admin
        self.client.force_login(user)

    def student_payload(self, **overrides):
        payload = {
            'full_name': self.student.full_name,
            'gender': 'male',
            'parent_phone': '01098765432',
            'student_phone': '01011111111',
            'education_type': 'general',
            'is_active': True,
        }
        payload.update(overrides)
        return payload


class GroupsCountAnnotationTest(AuditBaseTest):
    """DATA-01 — groups_count must not be inflated by a cartesian join."""

    def test_groups_count_correct_for_two_groups(self):
        StudentGroupEnrollment.objects.create(student=self.student, group=self.group)
        StudentGroupEnrollment.objects.create(student=self.student, group=self.group2)

        self.login()
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 200)
        listed = {s.student_id: s for s in response.context['students']}
        self.assertEqual(listed[self.student.student_id].groups_count, 2)

    def test_with_groups_filter_uses_correct_count(self):
        StudentGroupEnrollment.objects.create(student=self.student, group=self.group)
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group2, is_active=False,
        )
        other = Student.objects.create(
            student_code='AUD002', full_name='بدون مجموعة',
            gender='male', parent_phone='01000000000',
        )

        self.login()
        response = self.client.get(reverse('students:list'), {'status': 'with_groups'})
        ids = [s.student_id for s in response.context['students']]
        self.assertIn(self.student.student_id, ids)
        self.assertNotIn(other.student_id, ids)

        response = self.client.get(reverse('students:list'), {'status': 'no_groups'})
        ids = [s.student_id for s in response.context['students']]
        self.assertIn(other.student_id, ids)
        self.assertNotIn(self.student.student_id, ids)


class StudentListPaginationTest(AuditBaseTest):
    """PERF-01 — the list view must paginate instead of loading everything."""

    def test_list_is_paginated(self):
        for i in range(30):
            Student.objects.create(
                student_code=f'PAG{i:03d}',
                full_name=f'طالب {i}',
                gender='male',
                parent_phone='01000000000',
            )
        self.login()
        response = self.client.get(reverse('students:list'))
        self.assertEqual(response.status_code, 200)
        page = response.context['page_obj']
        self.assertEqual(page.number, 1)
        self.assertEqual(len(page.object_list), 25)
        self.assertTrue(response.context['is_paginated'])

        response2 = self.client.get(reverse('students:list'), {'page': 2})
        self.assertEqual(response2.context['page_obj'].number, 2)
        self.assertEqual(len(response2.context['page_obj'].object_list), 6)

    def test_pagination_preserves_filters(self):
        self.login()
        response = self.client.get(reverse('students:list'), {'search': 'التدقيق', 'page': 1})
        self.assertEqual(response.status_code, 200)
        self.assertIn('search=', response.context['filter_querystring'])
        self.assertNotIn('page=', response.context['filter_querystring'])


class StudentsListApiTest(AuditBaseTest):
    """PERF-02 — no barcodes in the list payload, real pagination."""

    def test_no_barcodes_and_pagination_present(self):
        self.login()
        response = self.client.get(reverse('students:api_list'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('pagination', data)
        self.assertGreaterEqual(len(data['students']), 1)
        for row in data['students']:
            self.assertNotIn('barcode_base64', row)

    def test_page_size_is_capped(self):
        self.login()
        response = self.client.get(reverse('students:api_list'), {'page_size': '9999'})
        self.assertEqual(response.json()['pagination']['page_size'], 100)

    def test_invalid_page_size_falls_back(self):
        self.login()
        response = self.client.get(reverse('students:api_list'), {'page_size': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['pagination']['page_size'], 25)


class ReEnrollmentTest(AuditBaseTest):
    """BUG-07 — re-enrolling a removed student, and editing existing terms."""

    def test_reenroll_reactivates_removed_enrollment(self):
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group, is_active=False,
        )
        self.login(self.supervisor)
        response = self.client.post(
            reverse('students:update', kwargs={'student_id': self.student.pk}),
            self.student_payload(groups=[self.group.group_id]),
        )
        self.assertEqual(response.status_code, 302)
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.is_active)

    def test_financial_edits_to_existing_enrollment_are_applied(self):
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group, financial_status='normal',
        )
        self.login(self.supervisor)
        payload = self.student_payload(groups=[self.group.group_id])
        payload[f'financial_status_{self.group.group_id}'] = 'symbolic'
        payload[f'custom_fee_{self.group.group_id}'] = '75.5'
        response = self.client.post(
            reverse('students:update', kwargs={'student_id': self.student.pk}),
            payload,
        )
        self.assertEqual(response.status_code, 302)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.financial_status, 'symbolic')
        self.assertEqual(enrollment.custom_fee, Decimal('75.50'))

    def test_existing_terms_kept_when_not_posted(self):
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group, financial_status='exempt',
        )
        self.login(self.supervisor)
        self.client.post(
            reverse('students:update', kwargs={'student_id': self.student.pk}),
            self.student_payload(groups=[self.group.group_id]),
        )
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.financial_status, 'exempt')


class BulkActionTest(AuditBaseTest):
    """AUTH-06 + BUG-08 — role check and a delete that really deletes."""

    def setUp(self):
        super().setUp()
        self.url = reverse('students:api_bulk_action')

    def test_teacher_is_forbidden(self):
        self.login(self.teacher_user)
        response = self.client.post(self.url, {
            'action': 'deactivate', 'student_ids[]': [self.student.pk],
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_delete_soft_deletes_into_recycle_bin(self):
        StudentGroupEnrollment.objects.create(student=self.student, group=self.group)
        self.login(self.supervisor)
        response = self.client.post(self.url, {
            'action': 'delete', 'student_ids[]': [self.student.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        deleted = Student.all_objects.get(pk=self.student.pk)
        self.assertIsNotNone(deleted.deleted_at)
        self.assertEqual(deleted.deleted_by, self.supervisor)
        self.assertFalse(
            StudentGroupEnrollment.objects.filter(
                student_id=self.student.pk, is_active=True,
            ).exists()
        )

    def test_unknown_action_rejected(self):
        self.login(self.supervisor)
        response = self.client.post(self.url, {
            'action': 'drop_table', 'student_ids[]': [self.student.pk],
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])


class ToggleStatusPermissionTest(AuditBaseTest):
    """AUTH-06 — student_toggle_status is a supervisor+ operation."""

    def test_teacher_forbidden(self):
        self.login(self.teacher_user)
        response = self.client.post(
            reverse('students:toggle_status', kwargs={'student_id': self.student.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_supervisor_allowed(self):
        self.login(self.supervisor)
        response = self.client.post(
            reverse('students:toggle_status', kwargs={'student_id': self.student.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)


class AddToGroupApiTest(AuditBaseTest):
    """AUTH-05 / DATA-06 / DATA-09 — role + financial_status + fee validation."""

    def setUp(self):
        super().setUp()
        self.url = reverse('students:api_add_to_group')

    def test_teacher_forbidden(self):
        self.login(self.teacher_user)
        response = self.client.post(self.url, {
            'student_id': self.student.pk,
            'group_id': self.group.group_id,
            'financial_status': 'exempt',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            StudentGroupEnrollment.objects.filter(student=self.student).exists()
        )

    def test_invalid_financial_status_rejected(self):
        self.login(self.supervisor)
        response = self.client.post(self.url, {
            'student_id': self.student.pk,
            'group_id': self.group.group_id,
            'financial_status': 'totally_free',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertFalse(
            StudentGroupEnrollment.objects.filter(student=self.student).exists()
        )

    def test_non_numeric_custom_fee_does_not_500(self):
        self.login(self.supervisor)
        response = self.client.post(self.url, {
            'student_id': self.student.pk,
            'group_id': self.group.group_id,
            'financial_status': 'symbolic',
            'custom_fee': 'مجاناً',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_valid_symbolic_enrollment_stores_decimal(self):
        self.login(self.supervisor)
        response = self.client.post(self.url, {
            'student_id': self.student.pk,
            'group_id': self.group.group_id,
            'financial_status': 'symbolic',
            'custom_fee': '99.99',
        })
        self.assertEqual(response.status_code, 200)
        enrollment = StudentGroupEnrollment.objects.get(
            student=self.student, group=self.group,
        )
        self.assertEqual(enrollment.custom_fee, Decimal('99.99'))
        self.assertIsInstance(enrollment.custom_fee, Decimal)

    def test_incompatible_gender_rejected(self):
        female_group = create_group_with_schedule(
            group_name='مجموعة بنات',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Monday',
            schedule_time=time(18, 0),
            standard_fee=Decimal('200.00'),
            gender_type='female',
        )
        self.login(self.supervisor)
        response = self.client.post(self.url, {
            'student_id': self.student.pk,
            'group_id': female_group.group_id,
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])


class RemoveFromGroupApiTest(AuditBaseTest):
    """AUTH-05 — un-enrolling requires supervisor+."""

    def test_teacher_forbidden(self):
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
        )
        self.login(self.teacher_user)
        response = self.client.post(
            reverse('students:api_remove_from_group'),
            {'enrollment_id': enrollment.pk},
        )
        self.assertEqual(response.status_code, 403)
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.is_active)


class EntitlementStatusApiTest(AuditBaseTest):
    """
    students:api_entitlement_status — replaces the old global
    activate/status subscription endpoints. Read-only, per-group.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse(
            'students:api_entitlement_status',
            kwargs={'student_id': self.student.pk},
        )

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 401))

    def test_lists_active_enrollments_only(self):
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group, financial_status='normal',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group2, is_active=False,
        )
        self.login(self.supervisor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        group_ids = [g['group_id'] for g in data['groups']]
        self.assertIn(self.group.group_id, group_ids)
        self.assertNotIn(self.group2.group_id, group_ids)

    def test_unknown_student_404(self):
        self.login(self.supervisor)
        response = self.client.get(
            reverse('students:api_entitlement_status', kwargs={'student_id': 999999})
        )
        self.assertEqual(response.status_code, 404)


class StudentDeleteEnrollmentTest(AuditBaseTest):
    """DATA-12 — soft delete must stop the student's enrollments."""

    def test_delete_deactivates_enrollments(self):
        enrollment = StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
        )
        self.login(self.supervisor)
        response = self.client.post(
            reverse('students:delete', kwargs={'student_id': self.student.pk})
        )
        self.assertEqual(response.status_code, 302)
        enrollment.refresh_from_db()
        self.assertFalse(enrollment.is_active)
        self.assertIsNotNone(
            Student.all_objects.get(pk=self.student.pk).deleted_at
        )


class StudentCodeUniquenessTest(AuditBaseTest):
    """DATA-02 / DATA-08 — soft-deleted codes and auto-generation."""

    def test_form_rejects_code_of_deleted_student(self):
        ghost = Student.objects.create(
            student_code='9999', full_name='طالب محذوف',
            gender='male', parent_phone='01000000000',
        )
        ghost.soft_delete(user=self.admin)

        form = StudentForm(data={
            'student_code': '9999',
            'full_name': 'طالب جديد',
            'gender': 'male',
            'parent_phone': '01000000001',
            'student_phone': '01000000002',
            'education_type': 'general',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('student_code', form.errors)
        self.assertIn('سلة المهملات', ' '.join(form.errors['student_code']))

    def test_generated_code_skips_deleted_codes(self):
        Student.objects.create(
            student_code='5000', full_name='طالب قديم',
            gender='male', parent_phone='01000000000',
        ).soft_delete(user=self.admin)
        self.assertEqual(Student.generate_next_code(), '5001')

    def test_save_retries_when_code_taken_concurrently(self):
        Student.objects.create(
            student_code='7000', full_name='حجز الكود',
            gender='male', parent_phone='01000000000',
        )
        original = Student.generate_next_code

        calls = {'n': 0}

        def racing_code(cls=None):
            calls['n'] += 1
            if calls['n'] == 1:
                # First suggestion collides with a row created "concurrently"
                Student.objects.create(
                    student_code='7001', full_name='سبقنا',
                    gender='male', parent_phone='01000000000',
                )
                return '7001'
            return original()

        Student.generate_next_code = staticmethod(racing_code)
        try:
            student = Student.objects.create(
                full_name='طالب متزامن', gender='male', parent_phone='01000000000',
            )
        finally:
            Student.generate_next_code = classmethod(original.__func__)

        self.assertEqual(student.student_code, '7002')
        self.assertGreaterEqual(calls['n'], 2)


class FinancialStatusChoicesTest(AuditBaseTest):
    """DATA-09 / DATA-10 — validated choices, no phantom 'per_session'."""

    def test_per_session_removed(self):
        values = dict(StudentGroupEnrollment.FINANCIAL_STATUS_CHOICES)
        self.assertNotIn('per_session', values)

    def test_normalize_rejects_unknown_values(self):
        self.assertEqual(normalize_financial_status('exempt'), 'exempt')
        self.assertEqual(normalize_financial_status('per_session'), 'normal')
        self.assertEqual(normalize_financial_status('anything'), 'normal')


class MoneyParsingTest(TestCase):
    """DATA-06 — money is always Decimal, never float, never a 500."""

    def test_parses_decimal(self):
        self.assertEqual(parse_money('12.345'), Decimal('12.35'))
        self.assertEqual(parse_money('0'), Decimal('0.00'))

    def test_rejects_garbage_and_negatives(self):
        self.assertIsNone(parse_money('abc'))
        self.assertIsNone(parse_money(''))
        self.assertIsNone(parse_money(None))
        self.assertIsNone(parse_money('-5'))
        self.assertIsNone(parse_money('NaN'))
        self.assertIsNone(parse_money('Infinity'))

    def test_default_is_returned(self):
        self.assertEqual(parse_money('x', default=Decimal('1')), Decimal('1'))


class PhoneNormalizationTest(TestCase):
    """DATA-28 — one stored phone format across both student forms."""

    def test_both_forms_store_the_same_format(self):
        full = StudentForm(data={
            'full_name': 'طالب',
            'gender': 'male',
            'parent_phone': '+201012345678',
            'student_phone': '01098765432',
            'education_type': 'general',
        })
        quick = StudentQuickForm(data={
            'full_name': 'طالب',
            'parent_phone': '+201012345678',
        })
        self.assertTrue(full.is_valid(), full.errors)
        self.assertTrue(quick.is_valid(), quick.errors)
        self.assertEqual(
            full.cleaned_data['parent_phone'],
            quick.cleaned_data['parent_phone'],
        )
        self.assertEqual(quick.cleaned_data['parent_phone'], '01012345678')

    def test_helper_formats(self):
        self.assertEqual(normalize_phone('01012345678'), '01012345678')
        self.assertEqual(normalize_phone('201012345678'), '01012345678')
        self.assertEqual(normalize_phone('+20 101 234 5678'), '01012345678')
        # non-Egyptian numbers are left alone rather than mangled
        self.assertEqual(normalize_phone('+441234567890'), '+441234567890')


class TotalPaidAmountTest(AuditBaseTest):
    """DATA-22 — partial payments count towards the total paid."""

    def test_partial_payments_are_included(self):
        Payment.objects.create(
            student=self.student, group=self.group,
            month=date.today().replace(day=1),
            amount_due=Decimal('200.00'), amount_paid=Decimal('200.00'),
            status='paid',
        )
        Payment.objects.create(
            student=self.student, group=self.group2,
            month=date.today().replace(day=1),
            amount_due=Decimal('300.00'), amount_paid=Decimal('120.00'),
            status='partial',
        )
        self.assertEqual(self.student.get_total_paid_amount(), Decimal('320.00'))



class StudentCreateInitialPaymentTest(AuditBaseTest):
    """
    The "تم الدفع" quick-registration flow at creation time — must go
    through the payment ledger (record_transaction / activate_payment)
    instead of writing amount_paid/status directly.
    """

    def test_initial_payment_creates_ledger_transaction(self):
        from apps.payments.models import PaymentTransaction

        self.login(self.supervisor)
        response = self.client.post(reverse('students:create'), {
            **self.student_payload(full_name='طالب دفعة أولى', student_code=''),
            'groups': [str(self.group.group_id)],
            f'financial_status_{self.group.group_id}': 'normal',
            f'initial_payment_{self.group.group_id}': '200.00',
            f'paid_on_{self.group.group_id}': '2026-08-01',
        })
        self.assertEqual(response.status_code, 302)

        student = Student.objects.get(full_name='طالب دفعة أولى')
        payment = Payment.objects.get(student=student, group=self.group)
        self.assertEqual(payment.status, 'paid')
        self.assertEqual(payment.amount_paid, Decimal('200.00'))
        self.assertIsNotNone(payment.cycle_id)
        self.assertEqual(payment.paid_on.isoformat(), '2026-08-01')

        txn = PaymentTransaction.objects.get(payment=payment)
        self.assertEqual(txn.amount, Decimal('200.00'))
        self.assertEqual(txn.created_by, self.supervisor)

    def test_overtyped_initial_payment_is_clamped_not_crashed(self):
        self.login(self.supervisor)
        response = self.client.post(reverse('students:create'), {
            **self.student_payload(full_name='طالب دفعة زائدة', student_code=''),
            'groups': [str(self.group.group_id)],
            f'financial_status_{self.group.group_id}': 'normal',
            f'initial_payment_{self.group.group_id}': '9999.00',
        })
        self.assertEqual(response.status_code, 302)

        student = Student.objects.get(full_name='طالب دفعة زائدة')
        payment = Payment.objects.get(student=student, group=self.group)
        self.assertEqual(payment.amount_paid, Decimal('200.00'))
        self.assertEqual(payment.status, 'paid')


class WhatsAppNumberTest(TestCase):
    """
    apps.students.utils.whatsapp_number — the single dial-ready formatter
    shared by every wa.me link and the WhatsApp API. A stored 01xxxxxxxxx
    handed straight to wa.me is a dead link, and a foreign number must never
    be re-prefixed with Egypt's code (DATA-28).
    """

    def test_local_egyptian_gets_country_code(self):
        from apps.students.utils import whatsapp_number
        self.assertEqual(whatsapp_number('01012345678'), '201012345678')

    def test_already_international_plus_is_kept(self):
        from apps.students.utils import whatsapp_number
        self.assertEqual(whatsapp_number('+966501234567'), '966501234567')

    def test_double_zero_prefix_stripped(self):
        from apps.students.utils import whatsapp_number
        self.assertEqual(whatsapp_number('00201012345678'), '201012345678')

    def test_already_prefixed_left_alone(self):
        from apps.students.utils import whatsapp_number
        self.assertEqual(whatsapp_number('201012345678'), '201012345678')

    def test_bare_ten_digits_gets_code(self):
        from apps.students.utils import whatsapp_number
        self.assertEqual(whatsapp_number('1012345678'), '201012345678')

    def test_empty_is_safe(self):
        from apps.students.utils import whatsapp_number
        self.assertEqual(whatsapp_number(''), '')
        self.assertEqual(whatsapp_number(None), '')

    def test_whatsapp_service_delegates_to_same_rule(self):
        """The API sender and the templates must agree, byte for byte."""
        from apps.notifications.services import WhatsAppService
        from apps.students.utils import whatsapp_number
        svc = WhatsAppService()
        for raw in ('01012345678', '+966501234567', '00201012345678', '1012345678'):
            self.assertEqual(svc._format_phone_number(raw), whatsapp_number(raw))

    def test_student_properties(self):
        student = Student.objects.create(
            student_code='WA001', full_name='طالب واتساب', gender='male',
            student_phone='01011112222', parent_phone='01033334444',
        )
        self.assertEqual(student.student_whatsapp, '201011112222')
        self.assertEqual(student.parent_whatsapp, '201033334444')
