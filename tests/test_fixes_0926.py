"""
Fixes from the 2026-09-26 UI walk-through: the reports print every filtered
row, rooms can be deleted again (never while in use), the full-payment
button shows what is still owed, and the logo no longer comes from a CDN
that answers 403.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import Attendance, Session
from apps.payments.models import Payment
from apps.students.models import Student
from apps.teachers.models import Room
from tests.test_attendance import AttendanceTestMixin

User = get_user_model()


class ReportPrintTests(AttendanceTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username='adm_print', password='TestPass123!', role='admin')
        self.client.login(username='adm_print', password='TestPass123!')

    def test_attendance_print_has_every_filtered_row_not_one_page(self):
        today = timezone.localdate()
        for i in range(30):   # more than the 25-row screen page
            session = Session.objects.create(group=self.group, session_date=today - timedelta(days=i))
            Attendance.objects.create(student=self.student, session=session, status='present',
                                      scan_time=timezone.now())
        r = self.client.get(reverse('reports:attendance') + '?print=1')
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'reports/list_print.html')
        self.assertEqual(len(r.context['rows']), 30)
        self.assertFalse(r.context['truncated'])

        r = self.client.get(reverse('reports:attendance') + f'?print=1&date_from={today}&date_to={today}')
        self.assertEqual(len(r.context['rows']), 1)
        self.assertIn(f'من {today}', r.context['filters'])

    def test_payments_print_respects_filters_and_shows_amounts(self):
        month = timezone.localdate().replace(day=1)
        Payment.objects.create(student=self.student, group=self.group, month=month,
                               amount_due=Decimal('200'), amount_paid=Decimal('125'))
        r = self.client.get(reverse('reports:payments') + f'?print=1&month={month:%Y-%m}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['rows']), 1)
        row = r.context['rows'][0]
        self.assertEqual(row[0], self.student.full_name)
        self.assertIn('75', row[5])   # remaining
        r = self.client.get(reverse('reports:payments') + '?print=1&month=2001-01')
        self.assertEqual(r.context['rows'], [])

    def test_both_report_pages_carry_the_print_button(self):
        for name in ('reports:attendance', 'reports:payments'):
            r = self.client.get(reverse(name) + '?page=2&status=present')
            self.assertContains(r, 'btn-export print')
            self.assertContains(r, 'status=present&print=1')
            self.assertNotContains(r, 'page=2&print=1')


class RoomDeleteTests(AttendanceTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        User.objects.create_user(username='adm_room', password='TestPass123!', role='admin')
        self.client.login(username='adm_room', password='TestPass123!')

    def test_room_list_shows_delete_button_to_admin(self):
        r = self.client.get(reverse('teachers:room_list'))
        self.assertContains(r, reverse('teachers:room_delete', args=[self.room.pk]))

    def test_room_used_by_an_active_group_is_not_deleted(self):
        r = self.client.post(reverse('teachers:room_delete', args=[self.room.pk]), follow=True)
        self.room.refresh_from_db()
        self.assertIsNone(self.room.deleted_at)
        self.assertContains(r, 'لا يمكن حذف القاعة')

    def test_free_room_goes_to_recycle_bin(self):
        free = Room.objects.create(name='قاعة فاضية', capacity=10)
        self.client.post(reverse('teachers:room_delete', args=[free.pk]))
        self.assertIsNotNone(Room.all_objects.get(pk=free.pk).deleted_at)


class FullPayButtonTests(AttendanceTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        User.objects.create_user(username='adm_pay', password='TestPass123!', role='admin')
        self.client.login(username='adm_pay', password='TestPass123!')

    def test_button_shows_remaining_after_partial_payment(self):
        month = timezone.localdate().replace(day=1)
        Payment.objects.create(student=self.student, group=self.group, month=month,
                               amount_due=Decimal('200'), amount_paid=Decimal('125'))
        r = self.client.get(reverse('payments:list') + f'?month={month:%Y-%m}')
        self.assertContains(r, 'data-remaining="75.00"')
        self.assertContains(r, 'تسديد الباقي')


class LogoTests(TestCase):

    def test_login_logo_is_served_locally(self):
        r = self.client.get(reverse('accounts:login'))
        self.assertNotContains(r, 'b-cdn.net')
        self.assertContains(r, 'icons/logo.svg')


class FinancialReportTests(AttendanceTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        User.objects.create_user(username='adm_fin', password='TestPass123!', role='admin')
        self.client.login(username='adm_fin', password='TestPass123!')

    def test_deleted_teacher_revenue_stays_in_the_table(self):
        Payment.objects.create(student=self.student, group=self.group,
                               month=timezone.localdate().replace(day=1),
                               amount_due=Decimal('200'), amount_paid=Decimal('200'))
        self.teacher.soft_delete()
        r = self.client.get(reverse('reports:financial'))
        row = next(t for t in r.context['teacher_stats'] if t['name'] == self.teacher.full_name)
        self.assertEqual(row['total_revenue'], Decimal('200'))
        self.assertTrue(row['is_deleted'])
        self.assertContains(r, 'محذوف')

    def test_month_names_are_arabic(self):
        import json
        r = self.client.get(reverse('reports:financial'))
        names = [m['month_name'] for m in json.loads(r.context['monthly_data'])]
        self.assertFalse(any(n.split()[0] in ('January', 'September', 'December') for n in names), names)


class ScannerExportDateTests(AttendanceTestMixin, TestCase):

    def test_export_dialog_defaults_to_cairo_today(self):
        self.client.login(username='sup_att', password='TestPass123!')
        r = self.client.get(reverse('attendance:scanner'))
        self.assertContains(r, f'id="exportDate" value="{timezone.localdate().isoformat()}"')


class RoleButtonTests(AttendanceTestMixin, TestCase):
    """Buttons a role cannot use are not shown to it (they used to 403)."""

    def setUp(self):
        super().setUp()
        User.objects.create_user(username='tch_btn', password='TestPass123!', role='teacher')

    def test_teacher_sees_no_edit_or_group_links(self):
        self.client.login(username='tch_btn', password='TestPass123!')
        r = self.client.get(reverse('students:list'))
        self.assertNotContains(r, reverse('students:update', args=[self.student.pk]))
        self.assertNotContains(r, reverse('teachers:group_detail', args=[self.group.pk]))
        r = self.client.get(reverse('teachers:list'))
        self.assertNotContains(r, reverse('teachers:update', args=[self.teacher.pk]))
        r = self.client.get(reverse('teachers:room_list'))
        self.assertNotContains(r, reverse('teachers:room_update', args=[self.room.pk]))

    def test_supervisor_edits_but_does_not_see_admin_deletes(self):
        self.client.login(username='sup_att', password='TestPass123!')
        r = self.client.get(reverse('teachers:list'))
        self.assertContains(r, reverse('teachers:update', args=[self.teacher.pk]))
        self.assertNotContains(r, reverse('teachers:delete', args=[self.teacher.pk]))
        r = self.client.get(reverse('teachers:group_list'))
        self.assertContains(r, reverse('teachers:group_detail', args=[self.group.pk]))
        self.assertNotContains(r, reverse('teachers:group_delete', args=[self.group.pk]))


class DeletedDuesTests(AttendanceTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        User.objects.create_user(username='adm_dues', password='TestPass123!', role='admin')
        self.client.login(username='adm_dues', password='TestPass123!')
        self.month = timezone.localdate().replace(day=1)

    def test_unpaid_due_of_a_deleted_student_leaves_the_totals_collected_money_stays(self):
        Payment.objects.create(student=self.student, group=self.group, month=self.month,
                               amount_due=Decimal('200'), amount_paid=Decimal('0'))
        gone = Student.objects.create(student_code='GONE1', full_name='طالب محذوف', gender='male',
                                      parent_phone='01098765400', student_phone='01011111100')
        Payment.objects.create(student=gone, group=self.group, month=self.month,
                               amount_due=Decimal('300'), amount_paid=Decimal('0'))
        paid_gone = Student.objects.create(student_code='GONE2', full_name='طالب محذوف دافع', gender='male',
                                           parent_phone='01098765401', student_phone='01011111101')
        Payment.objects.create(student=paid_gone, group=self.group, month=self.month,
                               amount_due=Decimal('100'), amount_paid=Decimal('100'))
        gone.soft_delete()
        paid_gone.soft_delete()
        r = self.client.get(reverse('reports:payments') + f'?month={self.month:%Y-%m}')
        self.assertEqual(r.context['total_due'], Decimal('300'))     # 200 live + 100 collected
        self.assertEqual(r.context['total_paid'], Decimal('100'))
        r = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(r.context['month_total_due'], Decimal('300'))


class DashboardAndHeadersTests(AttendanceTestMixin, TestCase):

    def setUp(self):
        super().setUp()
        User.objects.create_user(username='adm_dash', password='TestPass123!', role='admin')
        self.client.login(username='adm_dash', password='TestPass123!')

    def test_lessons_card_counts_the_same_timetable_as_the_table(self):
        r = self.client.get(reverse('reports:dashboard'))
        self.assertEqual(r.context['today_total_sessions'],
                         sum(1 for s in r.context['today_schedule'] if s['status'] != 'cancelled'))

    def test_day_names_are_arabic(self):
        r = self.client.get(reverse('reports:dashboard'))
        self.assertNotContains(r, 'activites')
        self.assertIn(r.context['today_day_name'], ('السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة'))

    def test_signed_in_pages_are_not_cached_and_carry_permissions_policy(self):
        r = self.client.get(reverse('reports:dashboard'))
        self.assertIn('no-store', r['Cache-Control'])
        self.assertIn('private', r['Cache-Control'])
        self.assertIn('camera=(self)', r['Permissions-Policy'])

    def test_payments_page_is_paginated(self):
        month = timezone.localdate().replace(day=1)
        for i in range(55):
            s = Student.objects.create(student_code=f'PG{i:03d}', full_name=f'طالب {i}', gender='male',
                                       parent_phone=f'0101234{i:04d}', student_phone='')
            Payment.objects.create(student=s, group=self.group, month=month,
                                   amount_due=Decimal('200'), amount_paid=Decimal('0'))
        r = self.client.get(reverse('payments:list') + f'?month={month:%Y-%m}')
        self.assertEqual(len(r.context['payments']), 50)
        self.assertContains(r, 'page=2')


class PhoneValidationTests(TestCase):

    def test_validate_phone(self):
        from django.core.exceptions import ValidationError
        from apps.students.utils import validate_phone
        self.assertEqual(validate_phone('+20 101 234 5678'), '01012345678')
        self.assertEqual(validate_phone('', required=False), '')
        for bad in ('0101', '01912345678', 'abc', '010123456789'):
            with self.assertRaises(ValidationError):
                validate_phone(bad)


class ErrorPageTests(TestCase):

    def test_404_uses_the_branded_page(self):
        User.objects.create_user(username='adm_404', password='TestPass123!', role='admin')
        self.client.login(username='adm_404', password='TestPass123!')
        with self.settings(DEBUG=False):
            r = self.client.get('/students/999999/')
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, 'icons/logo.svg', status_code=404)
        self.assertNotContains(r, "DEBUG = True", status_code=404)
