"""
Every page touched on 2026-10-14 (links in tables, print-all, refusal reason,
excuse labels) renders for an admin.
"""
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import Attendance, Session
from apps.payments.models import Payment
from apps.payments.services import SettlementService
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.cycles import assign_to_cycle
from apps.teachers.models import Room, Teacher
from tests.factories import create_group_with_schedule


@override_settings(FEATURE_UPDATE_PAID=True)
class PagesRenderTest(TestCase):

    def setUp(self):
        get_user_model().objects.create_user(username='boss14', password='pw12345!', role='admin')
        self.client.login(username='boss14', password='pw12345!')
        self.teacher = Teacher.objects.create(
            full_name='مدرس الروابط', phone='01000000000', email='l@t.com',
            specialization='Math', hire_date=timezone.localdate(),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة الروابط', teacher=self.teacher,
            room=Room.objects.create(name='قاعة الروابط', capacity=20),
            schedule_day='Saturday', schedule_time=time(10, 0), standard_fee=200,
            sessions_per_month=4,
        )
        self.student = Student.objects.create(student_code='L14', full_name='طالب الروابط',
                                              parent_phone='01000000001')
        StudentGroupEnrollment.objects.create(student=self.student, group=self.group)
        day = timezone.localdate() - timedelta(days=1)
        self.session = assign_to_cycle(Session.objects.create(group=self.group, session_date=day))
        Attendance.objects.create(student=self.student, session=self.session, status='absent',
                                  rejection_reason='payment', scan_time=timezone.now())
        Payment.objects.create(student=self.student, group=self.group, cycle=self.session.cycle,
                               month=day.replace(day=1), amount_due=200, amount_paid=200,
                               status='paid', paid_on=day)
        self.settlement = SettlementService.build_or_refresh(
            self.teacher, day.replace(day=1), timezone.localdate())

    def _urls(self):
        g, s, st = self.group.pk, self.session.pk, self.student.pk
        return [
            reverse('reports:dashboard'),
            reverse('reports:attendance'),
            reverse('reports:attendance') + '?print=1',
            reverse('reports:payments'),
            reverse('reports:comprehensive'),
            *[reverse('reports:comprehensive') + f'?detail={k}' for k in
              ('due', 'paid', 'remaining', 'unpaid', 'attended', 'present', 'late', 'absent')],
            reverse('reports:tsfya'),
            reverse('reports:activity_log') + '?print_all=1',
            reverse('reports:cycle_register') + f'?group={g}',
            reverse('payments:list') + '?print_all=1',
            reverse('payments:settlement_index'),
            reverse('payments:settlement_detail', args=[self.settlement.pk]),
            reverse('payments:settlement_print', args=[self.settlement.pk]),
            reverse('attendance:session_detail', args=[s]),
            reverse('attendance:group_roster_print', args=[g]),
            reverse('teachers:group_detail', args=[g]),
            reverse('teachers:list') + '?print_all=1',
            reverse('teachers:group_list') + '?print_all=1',
            reverse('teachers:detail', args=[self.teacher.pk]),
            reverse('students:list') + '?print_all=1',
            reverse('students:detail', args=[st]),
        ]

    def test_pages_render(self):
        for url in self._urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_refusal_reason_shown_on_lesson_page(self):
        r = self.client.get(reverse('attendance:session_detail', args=[self.session.pk]))
        self.assertContains(r, 'مُنع — مصروفات')


class ScheduleClashWarningTest(PagesRenderTest):
    """Two groups at the same hour: the student page says so."""

    def test_clash_shown_on_student_page(self):
        other = create_group_with_schedule(
            group_name='مجموعة متعارضة', teacher=self.teacher,
            room=Room.objects.create(name='قاعة تانية', capacity=20),
            schedule_day='Saturday', schedule_time=time(10, 30), standard_fee=200,
            sessions_per_month=4,
        )
        StudentGroupEnrollment.objects.create(student=self.student, group=other)
        r = self.client.get(reverse('students:detail', args=[self.student.pk]))
        self.assertContains(r, 'في مجموعتين في نفس الميعاد')


class DropoutsReportTest(PagesRenderTest):
    """A student absent from the last 3 lessons is listed; one who came is not."""

    def test_dropout_listed(self):
        for days in (8, 15):
            s = assign_to_cycle(Session.objects.create(
                group=self.group, session_date=timezone.localdate() - timedelta(days=days)))
            Attendance.objects.create(student=self.student, session=s, status='absent', scan_time=timezone.now())
        r = self.client.get(reverse('reports:dropouts'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([row['student'] for row in r.context['rows']], [self.student])
        self.assertEqual(r.context['rows'][0]['streak'], 3)

    def test_attending_student_not_listed(self):
        Attendance.objects.filter(student=self.student).update(status='present')
        r = self.client.get(reverse('reports:dropouts') + '?min=1')
        self.assertEqual(r.context['rows'], [])


class CycleSettlementBoxTest(PagesRenderTest):
    """The paper sheet carries its own teacher's account (client, 2026-10-27)."""

    def test_cycle_settlement_matches_payments(self):
        from apps.reports.views import _cycle_register_data, _cycle_settlement
        self.group.center_percentage = 30
        self.group.save()
        _, rows = _cycle_register_data(self.group, self.session.cycle)
        st = _cycle_settlement(self.group, rows)
        self.assertEqual((st['collected'], st['center'], st['teacher'], st['paying']),
                         (200, 60, 140, 1))
        r = self.client.get(reverse('reports:cycle_register') + f'?group={self.group.pk}')
        self.assertContains(r, 'تصفية الدورة')
