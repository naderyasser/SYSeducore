"""
«اربط كله بكله» (طلب العميل 2026-10-12): an edit to a group, a student's
terms in it, an attendance row or a payment reaches every stored number that
was computed from it — invoices, cycle size, entitlement, draft settlements —
and the activity log says what changed from what to what.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import ActivityLog, Attendance
from apps.attendance.services import AttendanceService
from apps.payments.models import Payment, TeacherSettlement
from apps.payments.services import SettlementService
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.cycles import open_cycle_for
from apps.teachers.forms import GroupForm
from apps.teachers.models import GroupCycle
from tests.test_attendance import AttendanceTestMixin


class LinkageBase(AttendanceTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='sup_att', password='TestPass123!')
        self.month = timezone.localdate().replace(day=1)

    def _student(self, code):
        student = Student.objects.create(
            student_code=code, full_name=f'طالب {code}', gender='male',
            parent_phone='01098765400', student_phone='01011111100',
        )
        StudentGroupEnrollment.objects.create(
            student=student, group=self.group, financial_status='normal', is_active=True,
        )
        return student

    def _invoice(self, student, cycle, **fields):
        data = {'amount_due': Decimal('200.00'), 'sessions_total': 4}
        data.update(fields)
        return Payment.objects.create(
            student=student, group=self.group, cycle=cycle, month=self.month, **data,
        )

    def _edit_group(self, **changes):
        form = GroupForm(instance=self.group)
        data = {}
        for name in form.fields:
            value = form[name].value()
            if isinstance(value, bool):
                if value:
                    data[name] = 'on'
                continue
            data[name] = '' if value is None else value
        data.update(changes)
        days = []
        for entry in self.group.get_schedule_entries():
            days.append(entry.day_of_week)
            data[f'schedule_time_{entry.day_of_week}'] = entry.start_time.strftime('%H:%M')
            data[f'schedule_duration_{entry.day_of_week}'] = str(entry.duration)
            if entry.room:
                data[f'schedule_room_{entry.day_of_week}'] = str(entry.room.pk)
        data['schedule_days[]'] = days
        return self.client.post(reverse('teachers:group_update', args=[self.group.pk]), data)


class GroupEditReachesInvoicesTests(LinkageBase):
    def test_new_price_reaches_unpaid_invoices_only(self):
        self._attend(-7)
        cycle = open_cycle_for(self.group)
        unpaid = self._invoice(self.student, cycle)
        paid = self._invoice(self._student('L2'), cycle, amount_paid=Decimal('200.00'), status='paid')
        discounted = self._invoice(self._student('L3'), cycle, amount_due=Decimal('150.00'))

        response = self._edit_group(standard_fee='300')
        self.assertEqual(response.status_code, 302)

        unpaid.refresh_from_db(); paid.refresh_from_db(); discounted.refresh_from_db()
        self.assertEqual((unpaid.amount_due, unpaid.status), (Decimal('300.00'), 'unpaid'))
        self.assertEqual((paid.amount_due, paid.status), (Decimal('200.00'), 'paid'))
        self.assertEqual(discounted.amount_due, Decimal('150.00'))

        log = ActivityLog.objects.filter(action='group_update').latest('created_at')
        self.assertIn('من 200 إلى 300', log.description)
        self.assertIn('1 فاتورة', log.description)

    def test_new_cycle_size_reaches_the_running_cycle_and_entitlements(self):
        self._attend(-7)
        cycle = open_cycle_for(self.group)
        full = self._invoice(self.student, cycle)
        # Joined at lesson 3 of 4: half the fee, 2 sessions.
        late = self._invoice(self._student('L2'), cycle, amount_due=Decimal('100.00'), sessions_total=2)
        paid = self._invoice(self._student('L3'), cycle, amount_paid=Decimal('200.00'), status='paid')

        self.assertEqual(self._edit_group(sessions_per_month='6').status_code, 302)

        cycle.refresh_from_db(); full.refresh_from_db(); late.refresh_from_db(); paid.refresh_from_db()
        self.assertEqual(cycle.sessions_planned, 6)
        self.assertEqual((full.amount_due, full.sessions_total), (Decimal('200.00'), 6))
        # Still joining at lesson 3 — now of 6: 4 sessions, 4/6 of the fee.
        self.assertEqual((late.amount_due, late.sessions_total), (Decimal('133.33'), 4))
        self.assertEqual((paid.amount_due, paid.sessions_total, paid.status), (Decimal('200.00'), 6, 'paid'))

    def test_cycle_cannot_shrink_below_lessons_already_held(self):
        for offset in (-9, -8, -7):
            self._attend(offset)
        response = self._edit_group(sessions_per_month='2')
        self.assertEqual(response.status_code, 200)
        self.group.refresh_from_db()
        self.assertEqual(self.group.sessions_per_month, 4)
        self.assertContains(response, 'اتعمل فيها 3 حصص')


class EnrollmentEditReachesInvoicesTests(LinkageBase):
    def test_financial_status_change_reprices_the_open_invoice(self):
        self._attend(-7)
        invoice = self._invoice(self.student, open_cycle_for(self.group))
        url = reverse('students:api_add_to_group')
        payload = {'student_id': self.student.pk, 'group_id': self.group.pk}

        self.client.post(url, {**payload, 'financial_status': 'exempt'})
        invoice.refresh_from_db()
        self.assertEqual((invoice.amount_due, invoice.is_exempt, invoice.status), (Decimal('0.00'), True, 'paid'))

        self.client.post(url, {**payload, 'financial_status': 'normal'})
        invoice.refresh_from_db()
        self.assertEqual((invoice.amount_due, invoice.is_exempt, invoice.status), (Decimal('200.00'), False, 'unpaid'))
        self.assertTrue(ActivityLog.objects.filter(description__contains='من معفي').exists()
                        or ActivityLog.objects.filter(description__contains='الحالة المالية: من').exists())

    def test_removal_drops_only_an_unused_invoice(self):
        self._attend(-7)
        cycle = open_cycle_for(self.group)
        unused = self._invoice(self.student, cycle)
        other = self._student('L2')
        used = self._invoice(other, cycle, sessions_attended=1)
        url = reverse('students:api_remove_from_group')

        self.client.post(url, {'enrollment_id': self.enrollment.pk})
        self.client.post(url, {'enrollment_id': StudentGroupEnrollment.objects.get(student=other).pk})

        self.assertFalse(Payment.objects.filter(pk=unused.pk).exists())
        self.assertTrue(Payment.objects.filter(pk=used.pk).exists())


class AttendanceEditReachesInvoicesTests(LinkageBase):
    def test_cancelling_an_attended_lesson_gives_it_back(self):
        first = self._attend(-8)
        second = self._attend(-7)
        invoice = self._invoice(self.student, open_cycle_for(self.group),
                                amount_paid=Decimal('200.00'), status='paid')
        AttendanceService.update_payment_sessions(self.student, self.group)
        invoice.refresh_from_db()
        self.assertEqual(invoice.sessions_attended, 2)

        response = self.client.post(
            reverse('attendance:cancel_session', args=[second.pk]), {'reason': 'عطل', 'notify': '0'},
        )
        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.sessions_attended, 1)
        self.assertTrue(Attendance.objects.filter(session=first).exists())

    def test_cancel_refused_on_a_closed_cycle_leaves_the_lesson_alone(self):
        session = self._attend(-7)
        cycle = session.cycle
        cycle.closed_on = session.session_date
        cycle.save(update_fields=['closed_on'])

        response = self.client.post(
            reverse('attendance:cancel_session', args=[session.pk]), {'notify': '0'},
        )
        self.assertEqual(response.status_code, 409)
        session.refresh_from_db()
        self.assertFalse(session.is_cancelled)

    def test_correction_in_a_closed_cycle_recounts_that_cycle_invoice(self):
        self._attend(-8)
        later = self._attend(-7)
        Attendance.objects.filter(session=later).delete()
        cycle = later.cycle
        invoice = self._invoice(self.student, cycle, amount_paid=Decimal('200.00'), status='paid',
                                sessions_attended=1)
        cycle.closed_on = later.session_date
        cycle.save(update_fields=['closed_on'])

        AttendanceService.record_manual(
            self.student, self.group, later.session_date, 'present', self.supervisor,
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.sessions_attended, 2)
        # Re-counted, never re-billed: no invoice appeared on another cycle.
        self.assertEqual(Payment.objects.filter(student=self.student).count(), 1)


class DraftSettlementFollowsTests(LinkageBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username='adm_link', password='TestPass123!', role='admin')
        self._attend(-7)
        self.cycle = open_cycle_for(self.group)
        self.invoice = self._invoice(self.student, self.cycle)
        start = self.cycle.started_on
        self.settlement = SettlementService.build_or_refresh(self.teacher, start, start + timedelta(days=30))

    def _collected(self):
        return self.settlement.lines.get(student=self.student).collected_amount

    def test_payment_refreshes_the_draft_it_feeds(self):
        self.assertEqual(self._collected(), Decimal('0.00'))
        with self.captureOnCommitCallbacks(execute=True):
            self.invoice.amount_paid = Decimal('200.00')
            self.invoice.status = 'paid'
            self.invoice.save()
        self.assertEqual(self._collected(), Decimal('200.00'))

    def test_opening_a_draft_shows_current_numbers(self):
        Payment.objects.filter(pk=self.invoice.pk).update(amount_paid=Decimal('200.00'), status='paid')
        self.client.login(username='adm_link', password='TestPass123!')
        self.assertEqual(
            self.client.get(reverse('payments:settlement_detail', args=[self.settlement.pk])).status_code, 200,
        )
        self.assertEqual(self._collected(), Decimal('200.00'))

    def test_approved_sheet_stays_frozen(self):
        TeacherSettlement.objects.filter(pk=self.settlement.pk).update(status=TeacherSettlement.STATUS_APPROVED)
        Payment.objects.filter(pk=self.invoice.pk).update(amount_paid=Decimal('200.00'), status='paid')
        self.client.login(username='adm_link', password='TestPass123!')
        self.client.get(reverse('payments:settlement_detail', args=[self.settlement.pk]))
        self.assertEqual(self._collected(), Decimal('0.00'))


class PackageCyclesTests(LinkageBase):
    """
    A package pre-creates the group's next cycles. Those reserved cycles used
    to be taken for the running one: the gate checked the wrong cycle, the
    next lesson tried to start a second open cycle, and the roll-over opened
    a brand-new cycle past them so the prepaid one never ran.
    """

    def test_package_does_not_hijack_the_running_cycle(self):
        from apps.attendance.tasks import roll_group_cycles

        self._attend(-7)
        running = open_cycle_for(self.group)
        self._invoice(self.student, running, amount_paid=Decimal('200.00'), status='paid')
        buyer = self._student('PKG')
        response = self.client.post(reverse('api_collect'), {
            'student_id': buyer.pk, 'group_id': self.group.pk,
            'amount': '400.00', 'package_cycles': '2',
        })
        self.assertTrue(response.json()['success'])
        reserved = GroupCycle.objects.get(group=self.group, index=running.index + 1)

        self.assertEqual(open_cycle_for(self.group), running)
        self.assertTrue(AttendanceService.check_financial_status(self.student, self.group)['allowed'])

        for offset in (-6, -5, -4):
            self.assertEqual(self._attend(offset).cycle, running)

        roll_group_cycles()
        running.refresh_from_db()
        self.assertIsNotNone(running.closed_on)
        self.assertEqual(open_cycle_for(self.group), reserved)
        self.assertEqual(GroupCycle.objects.filter(group=self.group).count(), 2)
        self.assertEqual(Payment.objects.get(student=buyer, cycle=reserved).status, 'paid')
        self.assertEqual(Payment.objects.get(student=self.student, cycle=reserved).status, 'unpaid')

    def test_second_package_reuses_the_reserved_cycle(self):
        self._attend(-7)
        url = reverse('api_collect')
        for code in ('PK1', 'PK2'):
            buyer = self._student(code)
            self.client.post(url, {
                'student_id': buyer.pk, 'group_id': self.group.pk,
                'amount': '400.00', 'package_cycles': '2',
            })
        self.assertEqual(GroupCycle.objects.filter(group=self.group).count(), 2)
