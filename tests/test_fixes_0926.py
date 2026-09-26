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
