"""
Tests for the client-requested UI/logic updates:

1. Teachers & groups directory — live search that bypasses pagination, and a
   "عرض" route into each group.
2. Educational stages & years — إعدادي is three years (not six), تأسيس and
   كورسات exist and carry no year at all.
3. Student registration & payment — partial payments, and an optional
   subscription date that falls back silently.

The stage/year rules are asserted at the *server* boundary (taxonomy helper →
form → stored value), not only in the rendered markup: the original bug was a
front-end one, but a fix that lives only in JavaScript is one stale POST away
from putting "السادس/إعدادي" back in the database.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core import education
from apps.payments.models import Payment
from apps.students.forms import StudentForm
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.forms import GroupForm
from apps.teachers.models import Group, GroupCycle, Room, Teacher
from apps.teachers.views import LIST_PAGE_SIZE
from tests.factories import create_group_with_schedule


# ═══════════════════════════════════════════════════════════════════════
# 2. Educational stages & academic years
# ═══════════════════════════════════════════════════════════════════════

class TestEducationTaxonomy(TestCase):
    """The stage → year table itself."""

    def test_preparatory_has_exactly_three_years(self):
        """The reported bug: إعدادي offered six years."""
        self.assertEqual(education.years_for_stage('preparatory'), ['1', '2', '3'])

    def test_primary_has_six_years(self):
        self.assertEqual(
            education.years_for_stage('primary'), ['1', '2', '3', '4', '5', '6'],
        )

    def test_secondary_has_three_years(self):
        self.assertEqual(education.years_for_stage('secondary'), ['1', '2', '3'])

    def test_foundation_and_courses_exist_as_stages(self):
        keys = dict(education.EDUCATION_STAGE_CHOICES)
        self.assertEqual(keys.get('foundation'), 'تأسيس')
        self.assertEqual(keys.get('courses'), 'كورسات')

    def test_foundation_and_courses_have_no_years(self):
        self.assertEqual(education.years_for_stage('foundation'), [])
        self.assertEqual(education.years_for_stage('courses'), [])
        self.assertFalse(education.stage_has_years('foundation'))
        self.assertFalse(education.stage_has_years('courses'))

    def test_unknown_or_blank_stage_offers_every_year(self):
        """
        A filter with no stage chosen must not hide rows, and a legacy record
        whose stage predates this table has to stay editable.
        """
        self.assertEqual(len(education.years_for_stage('')), 6)
        self.assertEqual(len(education.years_for_stage(None)), 6)

    def test_normalize_drops_a_year_the_stage_does_not_have(self):
        self.assertEqual(education.normalize_stage_year('preparatory', '6'), '')
        self.assertEqual(education.normalize_stage_year('secondary', '4'), '')

    def test_normalize_keeps_a_valid_pair(self):
        self.assertEqual(education.normalize_stage_year('preparatory', '3'), '3')
        self.assertEqual(education.normalize_stage_year('primary', '6'), '6')

    def test_normalize_blanks_year_for_year_less_stages(self):
        self.assertEqual(education.normalize_stage_year('foundation', '2'), '')
        self.assertEqual(education.normalize_stage_year('courses', '1'), '')

    def test_all_three_models_share_one_stage_list(self):
        """
        The three copies that used to drift apart are now the same object.
        """
        from apps.teachers.models import Subject

        self.assertIs(Student.EDUCATION_STAGE_CHOICES, education.EDUCATION_STAGE_CHOICES)
        self.assertIs(Group.EDUCATION_STAGE_CHOICES, education.EDUCATION_STAGE_CHOICES)
        self.assertIs(Subject.EDUCATION_STAGE_CHOICES, education.EDUCATION_STAGE_CHOICES)


class TestStageYearFormEnforcement(TestCase):
    """The rule survives a POST that ignores the front-end."""

    def _student_payload(self, **overrides):
        payload = {
            'full_name': 'طالب اختبار المرحلة',
            'gender': 'male',
            'student_phone': '01011111111',
            'parent_phone': '01022222222',
            'education_type': 'general',
            'is_active': True,
        }
        payload.update(overrides)
        return payload

    def test_student_form_blanks_year_six_under_preparatory(self):
        form = StudentForm(self._student_payload(
            education_stage='preparatory', education_year='6',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        student = form.save()
        self.assertEqual(student.education_stage, 'preparatory')
        self.assertEqual(student.education_year, '')

    def test_student_form_keeps_a_valid_preparatory_year(self):
        form = StudentForm(self._student_payload(
            education_stage='preparatory', education_year='3',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().education_year, '3')

    def test_student_form_accepts_foundation_and_blanks_the_year(self):
        form = StudentForm(self._student_payload(
            education_stage='foundation', education_year='2',
        ))
        self.assertTrue(form.is_valid(), form.errors)
        student = form.save()
        self.assertEqual(student.education_stage, 'foundation')
        self.assertEqual(student.education_year, '')

    def test_student_form_accepts_courses_stage(self):
        form = StudentForm(self._student_payload(education_stage='courses'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().education_stage, 'courses')

    def test_group_form_blanks_a_year_the_stage_does_not_have(self):
        teacher = Teacher.objects.create(
            full_name='مدرس المرحلة', phone='01033333333',
            specialization='رياضيات', hire_date=date(2024, 1, 1),
        )
        form = GroupForm({
            'group_name': 'مجموعة إعدادي',
            'teacher': teacher.pk,
            'duration_minutes': 120,
            'gender_type': 'mixed',
            'education_stage': 'preparatory',
            'education_year': '5',
            'standard_fee': '200',
            'center_percentage': '30',
            'sessions_per_month': 4,
            'is_active': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['education_year'], '')


class TestStageYearRendering(TestCase):
    """The taxonomy actually reaches the browser."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='stage_admin', password='pw12345', role='admin',
        )
        self.client.force_login(self.user)

    def test_stage_year_map_is_emitted_on_every_page(self):
        response = self.client.get(reverse('students:create'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="education-stage-years"', html)
        self.assertIn('education-stage-year.js', html)

    def test_student_form_offers_the_new_stages(self):
        html = self.client.get(reverse('students:create')).content.decode()
        self.assertIn('value="foundation"', html)
        self.assertIn('value="courses"', html)
        self.assertIn('تأسيس', html)
        self.assertIn('كورسات', html)

    def test_emitted_map_says_preparatory_has_three_years(self):
        response = self.client.get(reverse('students:create'))
        data = response.context['EDUCATION_STAGE_YEARS']
        self.assertEqual(len(data['preparatory']['short']), 3)
        self.assertEqual(len(data['primary']['short']), 6)
        self.assertEqual(data['foundation']['short'], [])

    def test_map_is_json_encoded_into_the_page(self):
        """Rendered through Django's json_script, which owns the escaping."""
        html = self.client.get(reverse('students:create')).content.decode()
        self.assertIn('id="education-stage-years"', html)
        self.assertIn('type="application/json"', html)


# ═══════════════════════════════════════════════════════════════════════
# 1. Teachers & groups directory search
# ═══════════════════════════════════════════════════════════════════════

class TestDirectorySearch(TestCase):
    """
    Searching returns *every* match, not the first page of them — the point of
    typing a teacher's name is to see all of their groups at once.
    """

    @classmethod
    def setUpTestData(cls):
        cls.room = Room.objects.create(name='قاعة البحث', capacity=40)
        cls.hunted = Teacher.objects.create(
            full_name='أحمد عبد الرحمن', phone='01055555555',
            specialization='رياضيات', hire_date=date(2024, 1, 1),
        )
        cls.other = Teacher.objects.create(
            full_name='محمود سيد', phone='01066666666',
            specialization='علوم', hire_date=date(2024, 1, 1),
        )
        # More groups than fit on one page, so a paginated response would
        # provably drop some of them.
        cls.group_count = LIST_PAGE_SIZE + 7
        for i in range(cls.group_count):
            create_group_with_schedule(
                group_name=f'مجموعة أحمد {i:02d}',
                teacher=cls.hunted, room=cls.room,
                schedule_day='Saturday', schedule_time=time(10, 0),
                standard_fee=Decimal('150.00'),
            )
        create_group_with_schedule(
            group_name='مجموعة محمود', teacher=cls.other, room=cls.room,
            schedule_day='Sunday', schedule_time=time(12, 0),
            standard_fee=Decimal('150.00'),
        )

    def setUp(self):
        self.user = User.objects.create_user(
            username='search_admin', password='pw12345', role='admin',
        )
        self.client.force_login(self.user)

    def test_group_list_is_paginated_without_a_search(self):
        response = self.client.get(reverse('teachers:group_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['groups']), LIST_PAGE_SIZE)

    def test_searching_a_teacher_returns_all_their_groups_unpaginated(self):
        response = self.client.get(
            reverse('teachers:group_list'), {'q': 'أحمد عبد الرحمن'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_search'])
        self.assertFalse(response.context['is_paginated'])
        self.assertEqual(len(response.context['groups']), self.group_count)

    def test_search_excludes_other_teachers_groups(self):
        response = self.client.get(
            reverse('teachers:group_list'), {'q': 'أحمد'},
        )
        names = [g.group_name for g in response.context['groups']]
        self.assertNotIn('مجموعة محمود', names)

    def test_search_matches_a_group_name_too(self):
        response = self.client.get(
            reverse('teachers:group_list'), {'q': 'مجموعة محمود'},
        )
        self.assertEqual(len(response.context['groups']), 1)

    def test_partial_response_needs_the_ajax_header(self):
        """
        ``partial=1`` alone must not hand out a chrome-less fragment — a stray
        link would otherwise render a page with no navigation at all.
        """
        full = self.client.get(
            reverse('teachers:group_list'), {'q': 'أحمد', 'partial': '1'},
        )
        self.assertContains(full, '<html', html=False)

        partial = self.client.get(
            reverse('teachers:group_list'),
            {'q': 'أحمد', 'partial': '1'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        body = partial.content.decode()
        self.assertNotIn('<html', body)
        self.assertIn('data-part="rows"', body)
        self.assertIn('data-part="meta"', body)

    def test_partial_rows_carry_a_table_wrapper(self):
        """
        The client parses the fragment with DOMParser, which silently discards
        a bare <tr>. The wrapper is what keeps the rows alive.
        """
        response = self.client.get(
            reverse('teachers:group_list'),
            {'q': 'أحمد', 'partial': '1'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        body = response.content.decode()
        self.assertIn('<tbody data-part="rows">', body)
        self.assertIn('<tr>', body)

    def test_group_rows_link_to_the_detail_page(self):
        response = self.client.get(reverse('teachers:group_list'))
        group = response.context['groups'][0]
        self.assertContains(
            response,
            reverse('teachers:group_detail', kwargs={'group_id': group.group_id}),
        )

    def test_teacher_search_lists_that_teachers_groups_inline(self):
        response = self.client.get(reverse('teachers:list'), {'q': 'أحمد'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_search'])
        teachers = list(response.context['teachers'])
        self.assertEqual(len(teachers), 1)
        self.assertEqual(len(teachers[0].visible_groups), self.group_count)
        self.assertContains(response, 'مجموعة أحمد 00')

    def test_search_join_does_not_corrupt_the_groups_count(self):
        """
        The search filters across the ``groups`` relation while the same
        queryset annotates a Count over it. Without ``distinct=True`` on that
        annotation the shared join multiplies the rows and the badge reports a
        different number when searching than when not.
        """
        plain = self.client.get(reverse('teachers:list'))
        unsearched = {t.pk: t.groups_count for t in plain.context['teachers']}

        searched = self.client.get(reverse('teachers:list'), {'q': 'أحمد'})
        for teacher in searched.context['teachers']:
            self.assertEqual(teacher.groups_count, unsearched[teacher.pk])
            self.assertEqual(teacher.groups_count, self.group_count)

    def test_group_search_does_not_duplicate_rows(self):
        """A teacher with several subjects must not multiply their groups."""
        from apps.teachers.models import Subject

        for name in ('جبر', 'هندسة', 'تفاضل'):
            self.hunted.subjects.add(Subject.objects.create(name=name))

        response = self.client.get(reverse('teachers:group_list'), {'q': 'أحمد'})
        ids = [g.group_id for g in response.context['groups']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), self.group_count)

    def test_teacher_list_without_search_does_not_expand_groups(self):
        response = self.client.get(reverse('teachers:list'))
        self.assertFalse(response.context['is_search'])
        self.assertNotContains(response, 'teacher-groups')

    def test_search_bar_is_present_on_both_directories(self):
        for url in (reverse('teachers:list'), reverse('teachers:group_list')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'directory-search-form')
                self.assertContains(response, 'name="q"')

    def test_no_results_reports_the_term(self):
        response = self.client.get(
            reverse('teachers:group_list'), {'q': 'لا يوجد مدرس بهذا الاسم'},
        )
        self.assertEqual(len(response.context['groups']), 0)
        self.assertContains(response, 'لا توجد مجموعات مطابقة')


class TestGroupDetailContent(TestCase):
    """The "عرض" destination shows what the client asked to see."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='detail_admin', password='pw12345', role='admin',
        )
        self.client.force_login(self.user)
        self.room = Room.objects.create(name='قاعة التفاصيل', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس التفاصيل', phone='01077777777',
            specialization='كيمياء', hire_date=date(2024, 1, 1),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة التفاصيل', teacher=self.teacher, room=self.room,
            schedule_day='Monday', schedule_time=time(16, 0),
            standard_fee=Decimal('300.00'), sessions_per_month=4,
        )
        self.student = Student.objects.create(
            student_code='DET001', full_name='طالب التفاصيل', gender='male',
            student_phone='01088888888', parent_phone='01099999999',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )
        self.cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4,
            started_on=timezone.localdate() - timedelta(days=5),
        )

    def test_reserved_cycle_says_it_has_not_started(self):
        """
        A cycle carries no start date until its first lesson is held, so a
        freshly opened one has ``started_on = None``. The page used to drop the
        line entirely, which read as "the start date is missing" rather than
        "this cycle has not begun" — and right after a rollover that is every
        group at once.
        """
        self.cycle.started_on = None
        self.cycle.save(update_fields=['started_on'])
        response = self.client.get(
            reverse('teachers:group_detail', kwargs={'group_id': self.group.group_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'لم تبدأ بعد')

    def test_detail_shows_roster_count_schedule_fee_and_start_date(self):
        response = self.client.get(
            reverse('teachers:group_detail', kwargs={'group_id': self.group.group_id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['enrolled_count'], 1)
        self.assertContains(response, 'طالب التفاصيل')      # student list
        self.assertContains(response, '300')                 # fee
        self.assertContains(response, self.cycle.started_on.strftime('%Y-%m-%d'))
        self.assertTrue(response.context['schedule_entries'])


class TestGroupDetailCollectedFees(TestCase):
    """
    "paid fees" on the group detail must mean *collected*, not *invoiced*.

    Once partial collection became possible, showing only ``amount_due`` next
    to a "جزئي" badge told the desk the price list and not how much of it had
    actually been taken.
    """

    def setUp(self):
        self.room = Room.objects.create(name='قاعة المحصل', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس المحصل', phone='01090001111',
            specialization='أحياء', hire_date=date(2024, 1, 1),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة المحصل', teacher=self.teacher, room=self.room,
            schedule_day='Sunday', schedule_time=time(15, 0),
            standard_fee=Decimal('100.00'), sessions_per_month=4,
        )
        self.cycle = GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4,
            started_on=timezone.localdate() - timedelta(days=3),
        )
        self.student = Student.objects.create(
            student_code='COL001', full_name='طالب المحصل', gender='male',
            student_phone='01090002222', parent_phone='01090003333',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )
        self.payment = Payment.objects.create(
            student=self.student, group=self.group, cycle=self.cycle,
            month=timezone.localdate().replace(day=1),
            amount_due=Decimal('100.00'), sessions_total=4,
        )
        self.payment.record_transaction(Decimal('40.00'), user=None)

    def _detail(self, user):
        self.client.force_login(user)
        return self.client.get(
            reverse('teachers:group_detail', kwargs={'group_id': self.group.group_id})
        )

    def test_row_carries_paid_and_remaining(self):
        admin = User.objects.create_user(
            username='col_admin', password='pw12345', role='admin',
        )
        response = self._detail(admin)
        self.assertEqual(response.status_code, 200)
        row = next(
            r for r in response.context['students_rows']
            if r['student'].pk == self.student.pk
        )
        self.assertEqual(row['payment_status'], 'partial')
        self.assertEqual(row['payment_amount_paid'], Decimal('40.00'))
        self.assertEqual(row['payment_remaining'], Decimal('60.00'))
        self.assertContains(response, 'باقي')

    def test_admin_sees_the_cycle_totals(self):
        admin = User.objects.create_user(
            username='col_admin2', password='pw12345', role='admin',
        )
        response = self._detail(admin)
        self.assertEqual(response.context['collected_total'], Decimal('40.00'))
        self.assertEqual(response.context['outstanding_total'], Decimal('60.00'))
        self.assertContains(response, 'المُحصَّل في الدورة')

    def test_supervisor_does_not_see_the_cycle_totals(self):
        """Cumulative money stays admin-only, as everywhere else."""
        supervisor = User.objects.create_user(
            username='col_sup', password='pw12345', role='supervisor',
        )
        response = self._detail(supervisor)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'المُحصَّل في الدورة')
        self.assertNotContains(response, 'المتبقي على الطلاب')

    def test_totals_are_absent_without_an_open_cycle(self):
        self.cycle.closed_on = timezone.localdate()
        self.cycle.save(update_fields=['closed_on'])
        admin = User.objects.create_user(
            username='col_admin3', password='pw12345', role='admin',
        )
        response = self._detail(admin)
        self.assertIsNone(response.context['collected_total'])


# ═══════════════════════════════════════════════════════════════════════
# 3. Student registration & payment
# ═══════════════════════════════════════════════════════════════════════

class TestPartialPayments(TestCase):
    """Paying part of a fee must be recordable, and must not raise."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='cashier', password='pw12345', role='supervisor',
        )
        self.client.force_login(self.user)
        self.room = Room.objects.create(name='قاعة الدفع', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس الدفع', phone='01044444444',
            specialization='لغات', hire_date=date(2024, 1, 1),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة الدفع', teacher=self.teacher, room=self.room,
            schedule_day='Tuesday', schedule_time=time(9, 0),
            standard_fee=Decimal('100.00'), sessions_per_month=4,
        )
        self.student = Student.objects.create(
            student_code='PAY001', full_name='طالب الدفع', gender='male',
            student_phone='01011112222', parent_phone='01033334444',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )
        self.payment = Payment.objects.create(
            student=self.student, group=self.group,
            month=timezone.localdate().replace(day=1),
            amount_due=Decimal('100.00'), sessions_total=4,
        )

    def test_paying_fifty_of_a_hundred_is_accepted(self):
        response = self.client.post(
            f'/api/payments/{self.payment.payment_id}/record/',
            {'amount': '50'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['status'], 'partial')
        self.assertEqual(Decimal(str(body['remaining'])), Decimal('50.00'))

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('50.00'))
        self.assertEqual(self.payment.status, 'partial')

    def test_a_second_partial_completes_the_payment(self):
        for amount in ('50', '50'):
            self.client.post(
                f'/api/payments/{self.payment.payment_id}/record/',
                {'amount': amount},
                headers={'x-requested-with': 'XMLHttpRequest'},
            )
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.amount_paid, Decimal('100.00'))

    def test_over_payment_is_still_refused_with_an_arabic_message(self):
        """Partial support must not become "any number is fine"."""
        response = self.client.post(
            f'/api/payments/{self.payment.payment_id}/record/',
            {'amount': '150'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount_paid, Decimal('0.00'))

    def test_partial_amount_input_is_rendered_on_the_payments_page(self):
        response = self.client.get(reverse('payments:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'partial-amount')
        self.assertContains(response, 'recordPartial(')

    def test_blank_date_defaults_to_today(self):
        self.client.post(
            f'/api/payments/{self.payment.payment_id}/record/',
            {'amount': '30'},
            headers={'x-requested-with': 'XMLHttpRequest'},
        )
        txn = self.payment.transactions.first()
        self.assertEqual(txn.effective_on, timezone.localdate())


class TestRegistrationSubscriptionDate(TestCase):
    """
    "تاريخ الاشتراك" is optional at registration and falls back silently.

    Note: the field the client described does not exist under that name — the
    only date collected during registration + payment is the per-group payment
    date, ``paid_on_<group_id>``, which this covers.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='reg_admin', password='pw12345', role='admin',
        )
        self.client.force_login(self.user)
        self.room = Room.objects.create(name='قاعة التسجيل', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس التسجيل', phone='01055556666',
            specialization='تاريخ', hire_date=date(2024, 1, 1),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة التسجيل', teacher=self.teacher, room=self.room,
            schedule_day='Wednesday', schedule_time=time(11, 0),
            standard_fee=Decimal('200.00'), sessions_per_month=4,
        )

    def _register(self, code, **extra):
        payload = {
            'student_code': code,
            'full_name': 'طالب التسجيل',
            'gender': 'male',
            'student_phone': '01012341234',
            'parent_phone': '01043214321',
            'education_type': 'general',
            'education_stage': 'preparatory',
            'education_year': '2',
            'is_active': 'on',
            'groups': [str(self.group.group_id)],
            f'financial_status_{self.group.group_id}': 'normal',
        }
        payload.update(extra)
        return self.client.post(reverse('students:create'), payload)

    def test_registration_succeeds_with_a_blank_subscription_date(self):
        response = self._register('REG001', **{
            f'initial_payment_{self.group.group_id}': '200',
            f'paid_on_{self.group.group_id}': '',
        })
        self.assertIn(response.status_code, (200, 302))
        student = Student.objects.get(student_code='REG001')
        payment = Payment.objects.get(student=student, group=self.group)
        self.assertEqual(payment.amount_paid, Decimal('200.00'))

    def test_blank_date_falls_back_to_the_cycle_start(self):
        cycle_start = timezone.localdate() - timedelta(days=6)
        GroupCycle.objects.create(
            group=self.group, index=1, sessions_planned=4, started_on=cycle_start,
        )
        self._register('REG002', **{
            f'initial_payment_{self.group.group_id}': '200',
            f'paid_on_{self.group.group_id}': '',
        })
        student = Student.objects.get(student_code='REG002')
        payment = Payment.objects.get(student=student, group=self.group)
        self.assertEqual(payment.transactions.first().effective_on, cycle_start)

    def test_an_explicit_date_still_wins(self):
        chosen = timezone.localdate() - timedelta(days=2)
        self._register('REG003', **{
            f'initial_payment_{self.group.group_id}': '200',
            f'paid_on_{self.group.group_id}': chosen.isoformat(),
        })
        student = Student.objects.get(student_code='REG003')
        payment = Payment.objects.get(student=student, group=self.group)
        self.assertEqual(payment.transactions.first().effective_on, chosen)

    def test_registration_accepts_a_partial_first_payment(self):
        self._register('REG004', **{
            f'initial_payment_{self.group.group_id}': '80',
        })
        student = Student.objects.get(student_code='REG004')
        payment = Payment.objects.get(student=student, group=self.group)
        self.assertEqual(payment.amount_paid, Decimal('80.00'))
        self.assertEqual(payment.status, 'partial')

    def test_registration_needs_no_payment_at_all(self):
        response = self._register('REG005')
        self.assertIn(response.status_code, (200, 302))
        self.assertTrue(Student.objects.filter(student_code='REG005').exists())


class TestSearchableDropdownMarkup(TestCase):
    """The teacher pickers are enhanced, and degrade to a plain <select>."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='combo_admin', password='pw12345', role='admin',
        )
        self.client.force_login(self.user)
        teacher = Teacher.objects.create(
            full_name='مدرس القائمة', phone='01066667777',
            specialization='جغرافيا', hire_date=date(2024, 1, 1),
        )
        # The group cascade filters (and the teacher picker inside them) only
        # render when there is at least one group to filter.
        create_group_with_schedule(
            group_name='مجموعة القائمة', teacher=teacher,
            room=Room.objects.create(name='قاعة القائمة', capacity=10),
            schedule_day='Thursday', schedule_time=time(13, 0),
            standard_fee=Decimal('100.00'),
        )

    def test_registration_teacher_filter_is_searchable(self):
        response = self.client.get(reverse('students:create'))
        self.assertContains(response, 'data-searchable')
        self.assertContains(response, 'searchable-select.js')

    def test_underlying_select_survives_for_no_js_users(self):
        html = self.client.get(reverse('students:create')).content.decode()
        self.assertIn('id="filter_teacher"', html)
        self.assertIn('مدرس القائمة', html)
