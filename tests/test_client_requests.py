"""
The three things the client asked for in one message: a student report, the
student's payments with their dates, and a search box that goes straight to
a teacher or group.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.payments.models import Payment, PaymentTransaction
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Group, GroupSchedule, Room, Teacher

User = get_user_model()


def _fixture():
    desk = User.objects.create_user(username='desk', password='pw12345!', role='admin')
    room = Room.objects.create(name='قاعة A', capacity=30)
    teacher = Teacher.objects.create(full_name='أ/ محمد عبد الرحمن', phone='01000000000',
                                     hire_date=datetime.date(2025, 9, 1))
    group = Group.objects.create(group_name='فيزياء ٣ ثانوي', teacher=teacher,
                                 schedule_day='Saturday', schedule_time=datetime.time(16, 0),
                                 duration_minutes=120, standard_fee=Decimal('50.00'), is_active=True)
    GroupSchedule.objects.create(group=group, day_of_week='Saturday',
                                 start_time=datetime.time(16, 0), duration=120, room=room)
    student = Student.objects.create(student_code='STU0001', full_name='أحمد على محمود',
                                     parent_phone='01111111110', education_stage='secondary',
                                     education_year='3')
    StudentGroupEnrollment.objects.create(student=student, group=group, is_active=True)
    return desk, teacher, group, student


class StudentPaymentStatementTests(TestCase):
    def setUp(self):
        self.desk, self.teacher, self.group, self.student = _fixture()
        self.client.login(username='desk', password='pw12345!')
        month = datetime.date(2026, 9, 1)
        self.partial = Payment.objects.create(
            student=self.student, group=self.group, month=month,
            amount_due=Decimal('1250.00'), amount_paid=Decimal('250.00'), status='partial')
        PaymentTransaction.objects.create(payment=self.partial, amount=Decimal('250.00'),
                                          effective_on=datetime.date(2026, 9, 3), created_by=self.desk)
        # An exempt row must not count as owed.
        Payment.objects.create(student=self.student, group=self.group,
                               month=datetime.date(2026, 8, 1), amount_due=Decimal('0.00'),
                               amount_paid=Decimal('0.00'), is_exempt=True, status='paid')

    def test_detail_page_lists_every_payment_with_its_dates(self):
        r = self.client.get(reverse('students:detail', kwargs={'student_id': self.student.pk}))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('سجل المدفوعات', body)
        self.assertIn('2026-09-03', body)                 # the transaction date
        self.assertIn('1,250\xa0ج.م', body)               # grouped, no trailing .00
        self.assertEqual(r.context['payment_totals']['count'], 2)

    def test_totals_skip_exempt_rows(self):
        r = self.client.get(reverse('students:detail', kwargs={'student_id': self.student.pk}))
        totals = r.context['payment_totals']
        self.assertEqual(totals['due'], Decimal('1250.00'))
        self.assertEqual(totals['paid'], Decimal('250.00'))
        self.assertEqual(totals['remaining'], Decimal('1000.00'))

    def test_report_page_renders_all_sections(self):
        r = self.client.get(reverse('students:report', kwargs={'student_id': self.student.pk}))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        for heading in ('البيانات الأساسية', 'البيانات الدراسية',
                        'المجموعات المسجل فيها', 'الحضور', 'كشف حساب المدفوعات'):
            self.assertIn(heading, body)
        self.assertIn(self.student.full_name, body)
        self.assertIn(self.teacher.full_name, body)
        self.assertIn('1,000\xa0ج.م', body)               # remaining in the footer

    def test_report_requires_login(self):
        self.client.logout()
        r = self.client.get(reverse('students:report', kwargs={'student_id': self.student.pk}))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])

    def test_detail_page_links_to_the_report(self):
        r = self.client.get(reverse('students:detail', kwargs={'student_id': self.student.pk}))
        self.assertIn(reverse('students:report', kwargs={'student_id': self.student.pk}),
                      r.content.decode())


class QuickSearchTests(TestCase):
    def setUp(self):
        self.desk, self.teacher, self.group, self.student = _fixture()
        self.client.login(username='desk', password='pw12345!')
        self.url = reverse('core:quick_search')

    def test_teacher_name_finds_teacher_and_their_groups(self):
        r = self.client.get(self.url, {'q': 'محمد'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual([t['label'] for t in data['teachers']['items']], [self.teacher.full_name])
        self.assertEqual(data['teachers']['items'][0]['url'],
                         reverse('teachers:detail', kwargs={'teacher_id': self.teacher.pk}))
        # The teacher's group surfaces under groups too — that is the shortcut
        # the desk asked for.
        self.assertEqual([g['label'] for g in data['groups']['items']], [self.group.group_name])

    def test_group_name_goes_straight_to_the_group(self):
        r = self.client.get(self.url, {'q': 'فيزياء'})
        data = r.json()
        self.assertEqual(data['groups']['items'][0]['url'],
                         reverse('teachers:group_detail', kwargs={'group_id': self.group.pk}))

    def test_student_by_code(self):
        r = self.client.get(self.url, {'q': 'STU0001'})
        data = r.json()
        self.assertEqual(data['students']['items'][0]['label'], self.student.full_name)

    def test_short_term_returns_nothing_rather_than_everything(self):
        r = self.client.get(self.url, {'q': 'م'})
        self.assertEqual(r.json(), {'q': 'م', 'groups': [], 'teachers': [], 'students': []})

    def test_more_flag_when_capped(self):
        for i in range(8):
            Student.objects.create(student_code=f'STU9{i:03d}', full_name=f'طالب تجريبي {i}',
                                   parent_phone=f'0122222222{i}')
        data = self.client.get(self.url, {'q': 'تجريبي'}).json()
        self.assertEqual(len(data['students']['items']), 6)
        self.assertTrue(data['students']['more'])
        self.assertIn('search=', data['more_urls']['students'])

    def test_requires_login(self):
        self.client.logout()
        r = self.client.get(self.url, {'q': 'محمد'})
        self.assertEqual(r.status_code, 302)

    def test_header_carries_the_search_box(self):
        r = self.client.get(reverse('students:list'))
        body = r.content.decode()
        self.assertIn('data-quick-search', body)
        self.assertIn(self.url, body)


class WhatsAppConnectionCardTests(TestCase):
    """The dashboard says whether the instance is linked, and to which phone."""

    def setUp(self):
        self.desk, *_ = _fixture()
        self.client.login(username='desk', password='pw12345!')
        from django.core.cache import cache
        cache.clear()

    def _dashboard(self, status):
        from unittest.mock import patch
        # settings_test turns WhatsApp off (the views redirect); this screen
        # is about the connection, so turn it on for the request.
        with patch('apps.notifications.views.WhatsAppService.get_instance_status',
                   return_value=status), \
             self.settings(NOTIFICATION_METHOD='whatsapp',
                           WHATSAPP_EXPECTED_NUMBER='01037526592'):
            return self.client.get(reverse('notifications:whatsapp_dashboard'))

    def test_working_instance_shows_green_and_matching_phone(self):
        r = self._dashboard({'success': True, 'status': 'WORKING', 'connected': True,
                             'phone': '201037526592@c.us', 'message': ''})
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('متصل', body)
        self.assertIn('مطابق', body)
        self.assertNotIn('لتشغيل الإرسال', body)

    def test_wrong_phone_is_called_out(self):
        r = self._dashboard({'success': True, 'status': 'WORKING', 'connected': True,
                             'phone': '201000000000@c.us', 'message': ''})
        self.assertIn('هاتف مختلف', r.content.decode())

    def test_api_error_is_shown_verbatim_with_the_steps(self):
        r = self._dashboard({'success': False,
                             'error': 'Unauthorized: The instance is not an API subscription.'})
        body = r.content.decode()
        self.assertIn('غير متصل', body)
        self.assertIn('not an API subscription', body)
        self.assertIn('لتشغيل الإرسال', body)
        self.assertIn('01037526592', body)

    def test_status_is_cached_for_a_minute(self):
        from unittest.mock import patch
        with patch('apps.notifications.views.WhatsAppService.get_instance_status',
                   return_value={'success': True, 'status': 'WORKING', 'connected': True,
                                 'phone': '', 'message': ''}) as probe, \
             self.settings(NOTIFICATION_METHOD='whatsapp'):
            self.client.get(reverse('notifications:whatsapp_dashboard'))
            self.client.get(reverse('notifications:whatsapp_dashboard'))
        self.assertEqual(probe.call_count, 1)
