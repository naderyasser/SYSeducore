"""
Client: «الجداول شكلها وحش» — the group page shows the paper sheet of the
chosen cycle, and the settlement sheet shows short dates instead of a column
of full ISO dates two screens tall.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.payments.models import TeacherSettlement, TeacherSettlementLine
from apps.students.models import Student
from apps.teachers.models import GroupCycle, Room, Teacher
from tests.factories import create_group_with_schedule


class PaperViewsTest(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username='paper_admin', password='TestPass123!', role='admin', is_superuser=True)
        self.client.force_login(self.admin)
        self.teacher = Teacher.objects.create(
            full_name='مدرس الورقة', phone='01234511111', specialization='عربي',
            hire_date=date(2024, 1, 1))
        self.group = create_group_with_schedule(
            group_name='مجموعة الورقة', teacher=self.teacher,
            room=Room.objects.create(name='قاعة الورقة', capacity=20),
            schedule_day='Saturday', schedule_time=time(10, 0),
            standard_fee=Decimal('200.00'), center_percentage=Decimal('30.00'))
        today = timezone.localdate()
        # creating the group already opened its first cycle — start it
        self.cycle = GroupCycle.objects.filter(group=self.group).order_by('index').first() \
            or GroupCycle.objects.create(group=self.group, index=1, sessions_planned=8)
        self.cycle.started_on = today - timedelta(days=10)
        self.cycle.save(update_fields=['started_on'])

    def test_group_page_embeds_the_paper_sheet_of_the_current_cycle(self):
        html = self.client.get(f'/teachers/groups/{self.group.pk}/').content.decode()
        self.assertIn('id="paper-frame"', html)
        self.assertIn(f'cycle={self.cycle.pk}&only=1&embed=1', html)

    def test_embedded_sheet_may_be_framed_by_this_site_and_has_no_menus(self):
        r = self.client.get(f'/reports/cycle-register/?group={self.group.pk}&cycle={self.cycle.pk}&only=1&embed=1')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['X-Frame-Options'], 'SAMEORIGIN')
        html = r.content.decode()
        self.assertIn('class="embed"', html)
        self.assertIn('<base target="_top">', html)

    def test_settlement_shows_short_dates_and_unpaid_tag(self):
        student = Student.objects.create(student_code='PPR001', full_name='طالب الورقة', parent_phone='01234511112')
        s = TeacherSettlement.objects.create(
            teacher=self.teacher, period_start=date(2026, 9, 1), period_end=date(2026, 9, 30))
        TeacherSettlementLine.objects.create(
            settlement=s, group=self.group, student=student, cycle=self.cycle,
            session_dates=['2026-09-06', '2026-09-09'], computed_amount=0, collected_amount=0)
        html = self.client.get(f'/payments/settlements/{s.pk}/').content.decode()
        self.assertIn('<span>9/6</span><span>9/9</span>', html)
        self.assertNotIn('2026-09-06', html)
        self.assertIn('لم يدفع', html)
