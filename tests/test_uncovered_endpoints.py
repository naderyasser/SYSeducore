"""
Ten functions no test had ever executed, found by running the suite under
coverage. Each is a real endpoint someone at the desk can hit; several guard
something that must not go wrong (the last admin, a permanent delete).
"""
import datetime
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.attendance.models import Attendance, ExceptionRecord, Session
from apps.payments.models import TeacherSettlement, TeacherSettlementLine
from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Group, GroupSchedule, Room, Subject, Teacher

User = get_user_model()


def _world():
    admin = User.objects.create_user(username='adm', password='pw12345!', role='admin')
    sup = User.objects.create_user(username='sup', password='pw12345!', role='supervisor')
    room = Room.objects.create(name='قاعة A', capacity=30)
    subject = Subject.objects.create(name='فيزياء', education_stage='secondary')
    teacher = Teacher.objects.create(full_name='أ/ محمد', phone='01000000000',
                                     hire_date=datetime.date(2025, 9, 1))
    teacher.subjects.add(subject)
    group = Group.objects.create(group_name='فيزياء ٣ ثانوي', teacher=teacher, schedule_day='Saturday',
                                 schedule_time=datetime.time(16, 0), duration_minutes=120,
                                 standard_fee=Decimal('50.00'), is_active=True,
                                 education_stage='secondary', education_year='3')
    GroupSchedule.objects.create(group=group, day_of_week='Saturday',
                                 start_time=datetime.time(16, 0), duration=120, room=room)
    student = Student.objects.create(student_code='STU0001', full_name='أحمد على',
                                     parent_phone='01111111110')
    StudentGroupEnrollment.objects.create(student=student, group=group, is_active=True)
    return admin, sup, teacher, subject, group, student


class UserToggleStatusTests(TestCase):
    def setUp(self):
        self.admin, self.sup, *_ = _world()
        self.client.login(username='adm', password='pw12345!')

    def _toggle(self, user):
        return self.client.post(reverse('accounts:user_toggle_status', kwargs={'user_id': user.pk}))

    def test_disables_and_re_enables_a_user(self):
        self._toggle(self.sup); self.sup.refresh_from_db()
        self.assertFalse(self.sup.is_active)
        self._toggle(self.sup); self.sup.refresh_from_db()
        self.assertTrue(self.sup.is_active)

    def test_cannot_disable_yourself(self):
        self._toggle(self.admin); self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_with_two_admins_one_may_be_disabled(self):
        other = User.objects.create_user(username='adm2', password='pw12345!', role='admin')
        self._toggle(other); other.refresh_from_db()
        self.assertFalse(other.is_active)

    def test_the_last_active_admin_cannot_be_disabled(self):
        # The actor must pass @admin_required without being a role=admin
        # themselves, or the self-guard fires first: a superuser whose role
        # is still the default "supervisor" is exactly that account.
        boss = User.objects.create_user(username='root', password='pw12345!',
                                        role='supervisor', is_superuser=True)
        self.client.logout(); self.client.login(username='root', password='pw12345!')
        self._toggle(self.admin); self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active, 'the only active admin must survive')

    def test_get_is_refused(self):
        r = self.client.get(reverse('accounts:user_toggle_status', kwargs={'user_id': self.sup.pk}))
        self.assertEqual(r.status_code, 302)
        self.sup.refresh_from_db(); self.assertTrue(self.sup.is_active)

    def test_supervisor_gets_403(self):
        self.client.logout(); self.client.login(username='sup', password='pw12345!')
        r = self._toggle(self.admin)
        self.assertEqual(r.status_code, 403)


class LastActiveAdminGuardTests(TestCase):
    def test_guard_logic_directly(self):
        from apps.accounts.views import _is_last_active_admin
        a = User.objects.create_user(username='a', password='x', role='admin')
        self.assertTrue(_is_last_active_admin(a))
        b = User.objects.create_user(username='b', password='x', role='admin')
        self.assertFalse(_is_last_active_admin(a))
        b.is_active = False; b.save()
        self.assertTrue(_is_last_active_admin(a))
        s = User.objects.create_user(username='s', password='x', role='supervisor')
        self.assertFalse(_is_last_active_admin(s))


class StudentHistoryApiTests(TestCase):
    def setUp(self):
        self.admin, self.sup, self.teacher, self.subject, self.group, self.student = _world()
        self.client.login(username='sup', password='pw12345!')
        session = Session.objects.create(group=self.group, session_date=datetime.date(2026, 9, 5))
        Attendance.objects.create(student=self.student, session=session, status='present',
                                  supervisor=self.sup)

    def test_returns_the_scans(self):
        r = self.client.get(reverse('api_student_history', kwargs={'student_id': self.student.pk}))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['student']['student_code'], 'STU0001')
        self.assertEqual(data['attendances'][0]['date'], '2026-09-05')
        self.assertEqual(data['attendances'][0]['status'], 'present')

    def test_unknown_student_is_a_json_404(self):
        r = self.client.get(reverse('api_student_history', kwargs={'student_id': 99999}))
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.json()['success'])


class RevokeExceptionTests(TestCase):
    def setUp(self):
        self.admin, self.sup, self.teacher, self.subject, self.group, self.student = _world()
        self.client.login(username='sup', password='pw12345!')

    def _exception(self):
        fields = {f.name for f in ExceptionRecord._meta.fields}
        kwargs = {'student': self.student, 'group': self.group}
        if 'reason' in fields:
            kwargs['reason'] = ExceptionRecord.PREDEFINED_REASON_CHOICES[0][0]
        if 'granted_by' in fields:
            kwargs['granted_by'] = self.sup
        if 'created_by' in fields:
            kwargs['created_by'] = self.sup
        return ExceptionRecord.objects.create(**kwargs)

    def test_revoke_deactivates_and_logs(self):
        exc = self._exception()
        r = self.client.post(reverse('attendance:revoke_exception', kwargs={'exception_id': exc.pk}))
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertTrue(r.json()['success'])
        exc.refresh_from_db(); self.assertFalse(exc.is_active)

    def test_missing_exception_is_json_404(self):
        r = self.client.post(reverse('attendance:revoke_exception', kwargs={'exception_id': 424242}))
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.json()['success'])

    def test_get_is_refused(self):
        exc = self._exception()
        r = self.client.get(reverse('attendance:revoke_exception', kwargs={'exception_id': exc.pk}))
        self.assertEqual(r.status_code, 405)


@override_settings(NOTIFICATION_METHOD='whatsapp')
class BulkCustomMessageTests(TestCase):
    def setUp(self):
        self.admin, self.sup, self.teacher, self.subject, self.group, self.student = _world()
        self.client.login(username='sup', password='pw12345!')
        self.url = reverse('notifications:bulk_custom_message')

    def _post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type='application/json')

    def test_bad_json_is_400(self):
        r = self.client.post(self.url, data='{not json', content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_empty_message_is_400(self):
        self.assertEqual(self._post({'message': '   '}).status_code, 400)

    def test_unknown_group_is_404(self):
        self.assertEqual(self._post({'message': 'x', 'group_id': 99999}).status_code, 404)
        self.assertEqual(self._post({'message': 'x', 'group_id': 'abc'}).status_code, 404)

    def test_group_send_is_queued_with_the_parents_numbers(self):
        with patch('apps.notifications.views._queue_bulk_send') as queue:
            queue.return_value = {'success': True, 'queued': 1}
            r = self._post({'message': 'تذكير', 'group_id': self.group.pk})
        self.assertEqual(r.status_code, 200, r.content[:200])
        self.assertTrue(queue.called)
        kwargs = queue.call_args.kwargs
        phones = [rcpt['phone'] if isinstance(rcpt, dict) else rcpt
                  for rcpt in (kwargs.get('recipients') or kwargs.get('phone_numbers') or [])]
        self.assertIn('01111111110', phones)


class SettlementPrintTests(TestCase):
    def setUp(self):
        self.admin, self.sup, self.teacher, self.subject, self.group, self.student = _world()
        self.client.login(username='adm', password='pw12345!')
        self.settlement = TeacherSettlement.objects.create(
            teacher=self.teacher, period_start=datetime.date(2026, 9, 1),
            period_end=datetime.date(2026, 9, 30), period_label='سبتمبر 2026',
            computed_gross=Decimal('1570.50'), adjusted_gross=Decimal('1570.50'),
            center_share=Decimal('471.15'), teacher_share=Decimal('1099.35'), created_by=self.admin)
        TeacherSettlementLine.objects.create(
            settlement=self.settlement, group=self.group, student=self.student,
            fee_full=Decimal('50.00'), computed_amount=Decimal('50.00'),
            collected_amount=Decimal('50.00'), effective_amount=Decimal('50.00'),
            line_center_share=Decimal('15.00'), line_teacher_share=Decimal('35.00'))

    def test_renders_with_grouped_lines_and_money(self):
        r = self.client.get(reverse('payments:settlement_print', kwargs={'settlement_id': self.settlement.pk}))
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn(self.group.group_name, body)
        self.assertIn(self.student.full_name, body)
        self.assertIn('1,099.35\xa0ج.م', body)

    def test_supervisor_is_refused(self):
        self.client.logout(); self.client.login(username='sup', password='pw12345!')
        r = self.client.get(reverse('payments:settlement_print', kwargs={'settlement_id': self.settlement.pk}))
        self.assertEqual(r.status_code, 403)


class RecyclePermanentDeleteTests(TestCase):
    def setUp(self):
        self.admin, self.sup, self.teacher, self.subject, self.group, self.student = _world()
        self.client.login(username='adm', password='pw12345!')
        self.url = reverse('reports:recycle_permanent_delete')

    def test_get_is_405_json(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 405)

    def test_missing_fields_and_bad_type(self):
        self.assertFalse(self.client.post(self.url, {}).json()['success'])
        self.assertFalse(self.client.post(self.url, {'type': 'planet', 'id': 1}).json()['success'])

    def test_refuses_an_item_that_is_not_in_the_bin(self):
        room = Room.objects.create(name='قاعة B', capacity=10)
        r = self.client.post(self.url, {'type': 'room', 'id': room.pk})
        self.assertFalse(r.json()['success'])
        self.assertTrue(Room.objects.filter(pk=room.pk).exists())

    def test_hard_deletes_a_binned_room(self):
        room = Room.objects.create(name='قاعة C', capacity=10)
        room.soft_delete()  # the instance's delete() is Django's hard delete
        self.assertTrue(Room.all_objects.get(pk=room.pk).is_deleted)
        r = self.client.post(self.url, {'type': 'room', 'id': room.pk})
        self.assertTrue(r.json()['success'], r.content[:200])
        self.assertFalse(Room.all_objects.filter(pk=room.pk).exists())

    def test_non_numeric_id_is_a_clean_json_answer(self):
        r = self.client.post(self.url, {'type': 'room', 'id': 'abc'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['success'])

    def test_supervisor_is_refused(self):
        self.client.logout(); self.client.login(username='sup', password='pw12345!')
        r = self.client.post(self.url, {'type': 'room', 'id': 1})
        self.assertIn(r.status_code, (401, 403))


class GroupsFilterApiTests(TestCase):
    def setUp(self):
        self.admin, self.sup, self.teacher, self.subject, self.group, self.student = _world()
        self.client.login(username='sup', password='pw12345!')
        self.url = reverse('api_groups_filter')

    def test_filters_by_stage_grade_teacher_subject(self):
        r = self.client.get(self.url, {'stage': 'secondary', 'grade': '3',
                                       'teacher_id': self.teacher.pk, 'subject_id': self.subject.pk})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        rows = data if isinstance(data, list) else data.get('results') or data.get('groups') or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], self.group.pk)
        self.assertIn('فيزياء', rows[0]['label'])

    def test_bad_ids_give_an_empty_list_not_a_500(self):
        for params in ({'teacher_id': 'abc'}, {'subject_id': 'x'}):
            r = self.client.get(self.url, params)
            self.assertEqual(r.status_code, 200, params)
            data = r.json()
            rows = data if isinstance(data, list) else data.get('results') or data.get('groups') or []
            self.assertEqual(rows, [])


class ServerErrorHelperTests(TestCase):
    def test_returns_generic_500_json_and_logs(self):
        from apps.teachers.api_views import _server_error, GENERIC_ERROR_MESSAGE
        with self.assertLogs('apps.teachers.api_views', level='ERROR'):
            r = _server_error('probe', RuntimeError('boom'))
        self.assertEqual(r.status_code, 500)
        self.assertEqual(json.loads(r.content)['error'], GENERIC_ERROR_MESSAGE)


class FinancialHistoryGuardTests(TestCase):
    def test_students_with_money_or_scans_are_blocked_from_purge(self):
        from apps.payments.models import Payment
        from apps.reports.views import _ids_with_financial_history
        admin, sup, teacher, subject, group, student = _world()
        clean = Student.objects.create(student_code='STU0002', full_name='بلا سجل', parent_phone='0100')
        Payment.objects.create(student=student, group=group, month=datetime.date(2026, 9, 1),
                               amount_due=Decimal('50.00'))
        blocked = _ids_with_financial_history(Student.objects.all())
        self.assertIn(student.pk, blocked)
        self.assertNotIn(clean.pk, blocked)
