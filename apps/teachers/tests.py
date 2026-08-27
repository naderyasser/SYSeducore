"""
Unit Tests for Teachers App - Educore V2
اختبار Room Model + Conflict Validation
"""

import json
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from apps.students.models import Student, StudentGroupEnrollment
from tests.factories import create_group_with_schedule

from .forms import GroupForm, TeacherForm
from .models import Group, GroupSchedule, Room, Subject, Teacher


class RoomModelTest(TestCase):
    """
    Unit Tests للـ Room Model
    """

    def test_create_room(self):
        """اختبار: إنشاء قاعة"""
        room = Room.objects.create(
            name='قاعة A',
            capacity=30
        )

        self.assertEqual(room.name, 'قاعة A')
        self.assertEqual(room.capacity, 30)
        self.assertTrue(room.is_active)

    def test_room_name_is_unique(self):
        """اختبار: اسم القاعة يجب أن يكون فريداً"""
        Room.objects.create(name='قاعة A', capacity=30)

        # محاولة إنشاء قاعة أخرى بنفس الاسم
        with self.assertRaises(IntegrityError):
            Room.objects.create(name='قاعة A', capacity=25)

    def test_room_str_representation(self):
        """اختبار: __str__ يرجع اسم القاعة"""
        room = Room.objects.create(name='قاعة B', capacity=25)
        self.assertEqual(str(room), 'قاعة B')


class GroupConflictValidationTest(TestCase):
    """
    Unit Tests لـ Conflict Validation
    اختبار منع التعارضات في جدول القاعات
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        # إنشاء مدرس
        self.teacher1 = Teacher.objects.create(
            full_name='محمد علي',
            email='teacher1@test.com',
            phone='+201234567890',
            specialization='رياضيات',
            hire_date='2020-01-01'
        )

        self.teacher2 = Teacher.objects.create(
            full_name='أحمد حسن',
            email='teacher2@test.com',
            phone='+201234567891',
            specialization='علوم',
            hire_date='2020-01-01'
        )

        # إنشاء قاعة
        self.room = Room.objects.create(
            name='قاعة A',
            capacity=30
        )

    def test_create_group_with_room(self):
        """اختبار: إنشاء مجموعة مع قاعة (القاعة على الموعد وليس المجموعة)"""
        group = create_group_with_schedule(
            group_name='مجموعة السبت',
            teacher=self.teacher1,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        entry = group.get_schedule_for_day('Saturday')
        self.assertEqual(entry.room, self.room)
        self.assertEqual(group.schedule_day, 'Saturday')

    def test_conflict_same_room_same_time(self):
        """اختبار: منع إنشاء موعدين في نفس القاعة + نفس اليوم + نفس الوقت"""
        group1 = create_group_with_schedule(
            group_name='مجموعة 1', teacher=self.teacher1, room=self.room,
            schedule_day='Saturday', schedule_time='09:00', standard_fee=200.00,
        )

        # محاولة حجز موعد ثانٍ بنفس القاعة والوقت — فحص التعارض الحقيقي عبر full_clean()
        with self.assertRaises((ValidationError, IntegrityError)):
            group2 = Group.objects.create(
                group_name='مجموعة 2', teacher=self.teacher2, standard_fee=200.00,
                schedule_day='Saturday', schedule_time='09:00',
            )
            schedule2 = GroupSchedule(
                group=group2, room=self.room,
                day_of_week='Saturday', start_time='09:00', duration=120,
            )
            schedule2.full_clean()

    def test_no_conflict_different_day(self):
        """اختبار: السماح بنفس القاعة والوقت لكن يوم مختلف"""
        create_group_with_schedule(
            group_name='مجموعة السبت', teacher=self.teacher1, room=self.room,
            schedule_day='Saturday', schedule_time='09:00', standard_fee=200.00,
        )

        group2 = Group.objects.create(
            group_name='مجموعة الأحد', teacher=self.teacher2, standard_fee=200.00,
            schedule_day='Sunday', schedule_time='09:00',
        )
        schedule2 = GroupSchedule(
            group=group2, room=self.room,
            day_of_week='Sunday', start_time='09:00', duration=120,  # يوم مختلف
        )
        schedule2.full_clean()
        schedule2.save()

        self.assertIsNotNone(schedule2.pk)  # تم الحفظ بنجاح

    def test_no_conflict_different_time(self):
        """اختبار: السماح بنفس القاعة واليوم لكن وقت مختلف"""
        create_group_with_schedule(
            group_name='مجموعة الصباح', teacher=self.teacher1, room=self.room,
            schedule_day='Saturday', schedule_time='09:00', standard_fee=200.00,
        )

        group2 = Group.objects.create(
            group_name='مجموعة الظهر', teacher=self.teacher2, standard_fee=200.00,
            schedule_day='Saturday', schedule_time='11:00',
        )
        schedule2 = GroupSchedule(
            group=group2, room=self.room,
            day_of_week='Saturday', start_time='11:00', duration=120,  # وقت مختلف
        )
        schedule2.full_clean()
        schedule2.save()

        self.assertIsNotNone(schedule2.pk)  # تم الحفظ بنجاح

    def test_no_conflict_no_room(self):
        """اختبار: السماح بمواعيد بدون قاعة"""
        group1 = create_group_with_schedule(
            group_name='مجموعة 1', teacher=self.teacher1, room=None,
            schedule_day='Saturday', schedule_time='09:00', standard_fee=200.00,
        )
        group2 = create_group_with_schedule(
            group_name='مجموعة 2', teacher=self.teacher2, room=None,
            schedule_day='Saturday', schedule_time='09:00', standard_fee=200.00,
        )

        # يجب السماح لأنه لا توجد قاعة
        self.assertIsNotNone(group1.pk)
        self.assertIsNotNone(group2.pk)

    def test_group_without_grace_period(self):
        """اختبار: المجموعة لا تحتوي على grace_period (النظام الثابت)"""
        group = create_group_with_schedule(
            group_name='مجموعة اختبار', teacher=self.teacher1, room=self.room,
            schedule_day='Saturday', schedule_time='09:00', standard_fee=200.00,
        )

        # التأكد أن grace_period غير موجود
        self.assertFalse(hasattr(group, 'grace_period'))


User = get_user_model()


class TeacherBlankEmailTest(TestCase):
    """DATA-03 — a second teacher without an email must not blow up."""

    def _form_data(self, **overrides):
        data = {
            'full_name': 'مدرس بدون بريد',
            'phone': '01000000000',
            'email': '',
            'specialization': 'رياضيات',
            'hire_date': '2024-01-01',
            'is_active': True,
        }
        data.update(overrides)
        return data

    def test_blank_email_is_stored_as_null(self):
        form = TeacherForm(self._form_data())
        self.assertTrue(form.is_valid(), form.errors)
        teacher = form.save()
        self.assertIsNone(teacher.email)

    def test_two_teachers_without_email(self):
        """كان المدرس الثاني بدون بريد يسبب IntegrityError"""
        first = TeacherForm(self._form_data())
        self.assertTrue(first.is_valid(), first.errors)
        first.save()

        second = TeacherForm(self._form_data(full_name='مدرس آخر', phone='01000000001'))
        self.assertTrue(second.is_valid(), second.errors)
        second.save()

        self.assertEqual(Teacher.objects.filter(email__isnull=True).count(), 2)

    def test_duplicate_email_is_a_form_error_not_a_crash(self):
        Teacher.objects.create(
            full_name='الأول', phone='0100', email='dup@test.com',
            hire_date=date(2024, 1, 1),
        )
        form = TeacherForm(self._form_data(email='dup@test.com'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_soft_deleted_email_reported_clearly(self):
        teacher = Teacher.objects.create(
            full_name='محذوف', phone='0101', email='gone@test.com',
            hire_date=date(2024, 1, 1),
        )
        teacher.soft_delete()
        form = TeacherForm(self._form_data(email='gone@test.com'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)


class GroupFormValidationTest(TestCase):
    """DATA-07 — fees and percentages need bounds."""

    def setUp(self):
        self.teacher = Teacher.objects.create(
            full_name='مدرس', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.room = Room.objects.create(name='قاعة الاختبار', capacity=20)

    def _data(self, **overrides):
        data = {
            'group_name': 'مجموعة',
            'teacher': self.teacher.pk,
            'duration_minutes': 120,
            'gender_type': 'mixed',
            'education_stage': '',
            'education_year': '',
            'standard_fee': '200',
            'center_percentage': '30',
            'sessions_per_month': 4,
            'is_active': True,
        }
        data.update(overrides)
        return data

    def test_negative_fee_rejected(self):
        form = GroupForm(self._data(standard_fee='-50'))
        self.assertFalse(form.is_valid())
        self.assertIn('standard_fee', form.errors)

    def test_percentage_above_100_rejected(self):
        form = GroupForm(self._data(center_percentage='500'))
        self.assertFalse(form.is_valid())
        self.assertIn('center_percentage', form.errors)

    def test_negative_percentage_rejected(self):
        form = GroupForm(self._data(center_percentage='-1'))
        self.assertFalse(form.is_valid())
        self.assertIn('center_percentage', form.errors)

    def test_zero_sessions_per_month_rejected(self):
        form = GroupForm(self._data(sessions_per_month=0))
        self.assertFalse(form.is_valid())
        self.assertIn('sessions_per_month', form.errors)

    def test_valid_bounds_accepted(self):
        form = GroupForm(self._data(standard_fee='0', center_percentage='100'))
        self.assertTrue(form.is_valid(), form.errors)


class GroupScheduleSourceOfTruthTest(TestCase):
    """DATA-04 / DATA-05 — GroupSchedule drives the timetable, and it validates."""

    def setUp(self):
        self.teacher = Teacher.objects.create(
            full_name='مدرس', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.other_teacher = Teacher.objects.create(
            full_name='مدرس آخر', phone='0101', hire_date=date(2024, 1, 1),
        )
        self.room = Room.objects.create(name='قاعة 1', capacity=30)

    def _form(self, **overrides):
        data = {
            'group_name': 'مجموعة',
            'teacher': self.teacher.pk,
            'duration_minutes': 120,
            'gender_type': 'mixed',
            'education_stage': '',
            'education_year': '',
            'standard_fee': '200',
            'center_percentage': '30',
            'sessions_per_month': 4,
            'is_active': True,
        }
        data.update(overrides)
        return GroupForm(data)

    def test_all_days_are_saved_and_readable(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        group = form.save_with_schedules([
            {'day': 'Saturday', 'time': time(14, 0), 'duration': 120, 'room': self.room},
            {'day': 'Monday', 'time': time(16, 0), 'duration': 90, 'room': self.room},
        ])

        self.assertEqual(group.schedules.count(), 2)
        entries = group.get_schedule_entries()
        self.assertEqual([e.day_of_week for e in entries], ['Saturday', 'Monday'])
        # legacy columns still point at the first session
        self.assertEqual(group.schedule_day, 'Saturday')
        self.assertEqual(group.schedule_time, time(14, 0))
        # the second day is reachable, which the legacy fields never exposed
        monday = group.get_schedule_for_day('Monday')
        self.assertIsNotNone(monday)
        self.assertEqual(monday.start_time, time(16, 0))
        self.assertEqual(monday.duration, 90)

    def test_double_booking_on_a_non_first_day_is_rejected(self):
        """كان التعارض في اليوم الثاني يمر بصمت"""
        first = self._form()
        self.assertTrue(first.is_valid(), first.errors)
        first.save_with_schedules([
            {'day': 'Saturday', 'time': time(14, 0), 'duration': 120, 'room': self.room},
            {'day': 'Monday', 'time': time(16, 0), 'duration': 120, 'room': self.room},
        ])

        second = self._form(group_name='مجموعة 2', teacher=self.other_teacher.pk)
        self.assertTrue(second.is_valid(), second.errors)
        with self.assertRaises(ValidationError):
            second.save_with_schedules([
                {'day': 'Monday', 'time': time(17, 0), 'duration': 120, 'room': self.room},
            ])

    def test_failed_schedule_save_is_rolled_back(self):
        """المجموعة يجب ألا تفقد جدولها إذا فشل الحفظ في المنتصف"""
        blocker_form = self._form(group_name='حاجز', teacher=self.other_teacher.pk)
        self.assertTrue(blocker_form.is_valid(), blocker_form.errors)
        blocker_form.save_with_schedules([
            {'day': 'Tuesday', 'time': time(10, 0), 'duration': 120, 'room': self.room},
        ])

        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        group = form.save_with_schedules([
            {'day': 'Saturday', 'time': time(14, 0), 'duration': 120, 'room': self.room},
        ])
        self.assertEqual(group.schedules.count(), 1)

        update = GroupForm(self._form().data, instance=group)
        self.assertTrue(update.is_valid(), update.errors)
        with self.assertRaises(ValidationError):
            update.save_with_schedules([
                {'day': 'Saturday', 'time': time(14, 0), 'duration': 120, 'room': self.room},
                {'day': 'Tuesday', 'time': time(10, 30), 'duration': 60, 'room': self.room},
            ])

        group.refresh_from_db()
        self.assertEqual(group.schedules.count(), 1)
        self.assertEqual(group.schedules.first().day_of_week, 'Saturday')

    def test_room_conflicts_are_reported_without_a_field_key(self):
        """
        الخطأ يجب أن يكون non-field وإلا يتحول إلى 500 عند عرض النموذج
        (``GroupForm`` لا يحتوي على حقل ``schedule_time``). هذا هو مسار
        ``Group.clean()`` الحقيقي الذي تستخدمه الفيوز — يقرأ الجدول المعلَّق
        عبر ``_pending_schedules`` قبل أن تُحفظ أي صفوف ``GroupSchedule``.
        """
        create_group_with_schedule(
            group_name='الأولى', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(9, 0),
            standard_fee=Decimal('100'),
        )
        clash = Group(
            group_name='الثانية', teacher=self.other_teacher,
            standard_fee=Decimal('100'),
        )
        clash._pending_schedules = [
            {'day': 'Saturday', 'time': time(9, 30), 'duration': 120, 'room': self.room},
        ]
        with self.assertRaises(ValidationError) as ctx:
            clash.full_clean()
        self.assertIn('__all__', ctx.exception.message_dict)

    def test_partial_save_skips_revalidation(self):
        """PERF-10 — soft delete must not re-run the whole model validation."""
        group = create_group_with_schedule(
            group_name='مجموعة', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(9, 0),
            standard_fee=Decimal('100'),
        )
        with self.assertNumQueries(1):
            group.save(update_fields=['deleted_at', 'deleted_by'])

    def test_conflict_check_can_be_skipped_without_skipping_other_rules(self):
        create_group_with_schedule(
            group_name='الأولى', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(9, 0),
            standard_fee=Decimal('100'),
        )
        clash = Group(
            group_name='الثانية', teacher=self.other_teacher,
            schedule_day='Saturday', schedule_time=time(9, 30),
            standard_fee=Decimal('100'),
        )
        clash.save(skip_conflict_check=True)
        self.assertIsNotNone(clash.pk)

        bad_year = Group(
            group_name='الثالثة', teacher=self.teacher,
            schedule_day='Friday', schedule_time=time(9, 0),
            standard_fee=Decimal('100'),
            education_stage='secondary', education_year='6',
        )
        with self.assertRaises(ValidationError):
            bad_year.save(skip_conflict_check=True)


class SubjectSoftDeleteTest(TestCase):
    """DATA-26 — deleting a subject must not silently wipe the teachers' M2M."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='subj_admin', password='TestPass123!', role='admin',
        )
        self.client = Client()
        self.client.force_login(self.admin)
        self.subject = Subject.objects.create(name='كيمياء', education_stage='secondary')
        self.teacher = Teacher.objects.create(
            full_name='مدرس', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.teacher.subjects.add(self.subject)

    def test_delete_is_soft_and_keeps_the_link(self):
        response = self.client.post(
            reverse('teachers:subject_delete', kwargs={'subject_id': self.subject.pk})
        )
        self.assertEqual(response.status_code, 302)

        self.assertFalse(Subject.objects.filter(pk=self.subject.pk).exists())
        revived = Subject.all_objects.get(pk=self.subject.pk)
        self.assertIsNotNone(revived.deleted_at)
        # the M2M row survives, so restoring brings the link back
        revived.restore()
        self.assertIn(revived, self.teacher.subjects.all())

    def test_confirm_page_reports_the_m2m_impact(self):
        response = self.client.get(
            reverse('teachers:subject_delete', kwargs={'subject_id': self.subject.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['linked_teachers_count'], 1)


class TeachersRoleAccessTest(TestCase):
    """AUTH-07 — a teacher-role account must not mutate teachers/rooms/groups."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='acl_admin', password='TestPass123!', role='admin',
        )
        self.supervisor = User.objects.create_user(
            username='acl_supervisor', password='TestPass123!', role='supervisor',
        )
        self.teacher_user = User.objects.create_user(
            username='acl_teacher', password='TestPass123!', role='teacher',
        )
        self.teacher = Teacher.objects.create(
            full_name='مدرس', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.room = Room.objects.create(name='قاعة ACL', capacity=20)
        self.group = create_group_with_schedule(
            group_name='مجموعة ACL', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(9, 0),
            standard_fee=Decimal('100'),
        )

    def test_teacher_role_cannot_reach_create_screens(self):
        self.client.force_login(self.teacher_user)
        for url in [
            reverse('teachers:create'),
            reverse('teachers:room_create'),
            reverse('teachers:group_create'),
            reverse('teachers:subject_create'),
            reverse('teachers:booking_create'),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_teacher_role_cannot_delete(self):
        self.client.force_login(self.teacher_user)
        deletes = [
            reverse('teachers:delete', kwargs={'teacher_id': self.teacher.pk}),
            reverse('teachers:room_delete', kwargs={'room_id': self.room.pk}),
            reverse('teachers:group_delete', kwargs={'group_id': self.group.pk}),
        ]
        for url in deletes:
            self.assertEqual(self.client.post(url).status_code, 403, url)
        self.assertTrue(Teacher.objects.filter(pk=self.teacher.pk).exists())
        self.assertTrue(Room.objects.filter(pk=self.room.pk).exists())
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())

    def test_supervisor_cannot_delete_but_can_create(self):
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse('teachers:group_create')).status_code, 200)
        self.assertEqual(
            self.client.post(
                reverse('teachers:delete', kwargs={'teacher_id': self.teacher.pk})
            ).status_code,
            403,
        )

    def test_teacher_role_can_still_read(self):
        self.client.force_login(self.teacher_user)
        for url in [
            reverse('teachers:list'),
            reverse('teachers:room_list'),
            reverse('teachers:group_list'),
            reverse('teachers:booking_calendar'),
        ]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_enroll_endpoint_returns_json_403_for_teacher_role(self):
        self.client.force_login(self.teacher_user)
        response = self.client.post(
            reverse('teachers:booking_student_enroll'),
            data=json.dumps({'group_id': self.group.pk, 'student_id': 1}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['success'])


class BookingCreateTest(TestCase):
    """BUG-01 — the booking flow used to raise TypeError on every submission."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='booking_admin', password='TestPass123!', role='admin',
        )
        self.client.force_login(self.admin)
        self.teacher = Teacher.objects.create(
            full_name='مدرس الحجز', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.other_teacher = Teacher.objects.create(
            full_name='مدرس آخر', phone='0101', hire_date=date(2024, 1, 1),
        )
        self.room = Room.objects.create(name='قاعة الحجز', capacity=20)
        self.student = Student.objects.create(
            student_code='BK001', full_name='طالب الحجز',
            gender='male', parent_phone='01099999999',
        )

    def _payload(self, **overrides):
        data = {
            'group_name': 'مجموعة الحجز',
            'subject_name': 'فيزياء',
            'duration_minutes': '120',
            'standard_fee': '250',
            'center_percentage': '30',
            'gender_type': 'mixed',
            'education_stage': 'secondary',
            'education_year': '1',
            'schedules': json.dumps([
                {'day': 'Saturday', 'time': '14:00', 'room': self.room.pk},
                {'day': 'Monday', 'time': '16:00', 'room': self.room.pk},
            ]),
        }
        data.update(overrides)
        return data

    def test_creates_one_group_with_all_its_days(self):
        url = reverse(
            'teachers:booking_create_for_teacher',
            kwargs={'teacher_id': self.teacher.pk},
        )
        response = self.client.post(url, self._payload())
        self.assertEqual(response.status_code, 302)

        group = Group.objects.get(group_name='مجموعة الحجز')
        self.assertEqual(group.teacher, self.teacher)
        self.assertEqual(group.get_schedule_for_day('Saturday').room, self.room)
        self.assertEqual(group.get_schedule_for_day('Monday').room, self.room)
        self.assertEqual(group.standard_fee, Decimal('250'))
        self.assertEqual(group.schedules.count(), 2)
        self.assertEqual(group.schedule_day, 'Saturday')

    def test_subject_is_attached_to_the_teacher(self):
        url = reverse(
            'teachers:booking_create_for_teacher',
            kwargs={'teacher_id': self.teacher.pk},
        )
        self.client.post(url, self._payload())
        self.assertTrue(self.teacher.subjects.filter(name='فيزياء').exists())

    def test_same_subject_name_in_two_stages_does_not_explode(self):
        """DATA-27 — get_or_create(name=...) ignored the composite unique key."""
        Subject.objects.create(name='فيزياء', education_stage='preparatory')
        Subject.objects.create(name='فيزياء', education_stage='secondary')
        url = reverse(
            'teachers:booking_create_for_teacher',
            kwargs={'teacher_id': self.teacher.pk},
        )
        response = self.client.post(url, self._payload())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            self.teacher.subjects.filter(name='فيزياء', education_stage='secondary').exists()
        )

    def test_enrols_the_selected_student(self):
        url = reverse(
            'teachers:booking_create_for_teacher',
            kwargs={'teacher_id': self.teacher.pk},
        )
        self.client.post(url, self._payload(
            student_id=self.student.pk, financial_status='symbolic',
        ))
        group = Group.objects.get(group_name='مجموعة الحجز')
        enrollment = StudentGroupEnrollment.objects.get(student=self.student, group=group)
        self.assertTrue(enrollment.is_active)
        self.assertEqual(enrollment.financial_status, 'symbolic')

    def test_teacher_is_required(self):
        """كان النظام يختار مدرساً عشوائياً عندما لا يُحدَّد مدرس"""
        response = self.client.post(reverse('teachers:booking_create'), self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Group.objects.filter(group_name='مجموعة الحجز').exists())

    def test_teacher_can_be_chosen_from_the_form(self):
        response = self.client.post(
            reverse('teachers:booking_create'),
            self._payload(teacher=self.other_teacher.pk),
        )
        self.assertEqual(response.status_code, 302)
        group = Group.objects.get(group_name='مجموعة الحجز')
        self.assertEqual(group.teacher, self.other_teacher)

    def test_validation_errors_are_shown_not_swallowed(self):
        response = self.client.post(
            reverse('teachers:booking_create_for_teacher',
                    kwargs={'teacher_id': self.teacher.pk}),
            self._payload(standard_fee='-100'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Group.objects.filter(group_name='مجموعة الحجز').exists())
        rendered = response.content.decode()
        self.assertIn('سالب', rendered)

    def test_room_double_booking_is_refused(self):
        url = reverse(
            'teachers:booking_create_for_teacher',
            kwargs={'teacher_id': self.teacher.pk},
        )
        self.client.post(url, self._payload())
        response = self.client.post(url, self._payload(
            group_name='مجموعة متعارضة',
            schedules=json.dumps([{'day': 'Monday', 'time': '16:30', 'room': self.room.pk}]),
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Group.objects.filter(group_name='مجموعة متعارضة').exists())


class BookingCalendarTest(TestCase):
    """DATA-04 — every day of a multi-day group must appear on the calendar."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='cal_admin', password='TestPass123!', role='admin',
        )
        self.client.force_login(self.admin)
        self.teacher = Teacher.objects.create(
            full_name='مدرس التقويم', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.room = Room.objects.create(name='قاعة التقويم', capacity=20)
        self.group = Group.objects.create(
            group_name='مجموعة متعددة الأيام', teacher=self.teacher,
            schedule_day='Saturday', schedule_time=time(14, 0),
            standard_fee=Decimal('100'),
        )
        for day, start in [('Saturday', time(14, 0)), ('Monday', time(16, 0))]:
            GroupSchedule.objects.create(
                group=self.group, day_of_week=day, start_time=start, duration=120,
                room=self.room,
            )

    def test_group_shows_on_every_scheduled_day(self):
        response = self.client.get(reverse('teachers:booking_calendar'))
        self.assertEqual(response.status_code, 200)
        by_day = {day['name']: day['groups'] for day in response.context['calendar_days']}
        self.assertEqual(len(by_day['Saturday']), 1)
        self.assertEqual(len(by_day['Monday']), 1)
        self.assertEqual(by_day['Monday'][0]['time'], '04:00 PM')
        self.assertEqual(by_day['Sunday'], [])


class RoomCapacityTest(TestCase):
    """DATA-29 — capacity is per session, not the sum across the week."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='cap_admin', password='TestPass123!', role='admin',
        )
        self.client.force_login(self.admin)
        self.teacher = Teacher.objects.create(
            full_name='مدرس السعة', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.room = Room.objects.create(name='قاعة السعة', capacity=10)
        self.groups = []
        for index, (day, start) in enumerate([
            ('Saturday', time(9, 0)), ('Sunday', time(9, 0)), ('Monday', time(9, 0)),
        ]):
            group = Group.objects.create(
                group_name=f'مجموعة {index}', teacher=self.teacher,
                schedule_day=day, schedule_time=start, standard_fee=Decimal('100'),
            )
            GroupSchedule.objects.create(
                group=group, day_of_week=day, start_time=start, duration=120,
                room=self.room,
            )
            self.groups.append(group)

        # 6 students in each of the 3 groups: 18 in total, but only 6 per session
        for index in range(6):
            student = Student.objects.create(
                student_code=f'CAP{index:03d}', full_name=f'طالب {index}',
                gender='male', parent_phone='01099999999',
            )
            for group in self.groups:
                StudentGroupEnrollment.objects.create(
                    student=student, group=group, is_active=True,
                )

    def test_room_detail_uses_per_session_capacity(self):
        response = self.client.get(
            reverse('teachers:room_detail', kwargs={'room_id': self.room.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_students'], 6)
        self.assertEqual(response.context['capacity_available'], 4)
        self.assertEqual(response.context['distinct_students_count'], 6)
        self.assertEqual(response.context['sessions_per_week'], 3)

    def test_room_apis_use_per_session_capacity(self):
        detail = self.client.get(
            reverse('teachers:api_room_detail', kwargs={'room_id': self.room.pk})
        ).json()
        self.assertEqual(detail['room']['capacity_used'], 6)
        self.assertEqual(detail['room']['capacity_available'], 4)
        self.assertEqual(detail['room']['sessions_per_week'], 3)

        stats = self.client.get(reverse('teachers:api_room_statistics')).json()
        self.assertEqual(stats['statistics']['total_capacity_used'], 6)
        self.assertEqual(stats['statistics']['full_rooms_count'], 0)

    def test_room_schedule_api_lists_every_day(self):
        payload = self.client.get(
            reverse('teachers:api_room_schedule', kwargs={'room_id': self.room.pk})
        ).json()
        self.assertTrue(payload['success'])
        self.assertEqual(sorted(payload['schedule'].keys()),
                         sorted(['Saturday', 'Sunday', 'Monday']))
        self.assertEqual(payload['schedule']['Monday']['sessions'][0]['students_count'], 6)


class RoomAvailabilityApiTest(TestCase):
    """DATA-04 — the availability check must see days 2..n of a group."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='avail_admin', password='TestPass123!', role='admin',
        )
        self.client.force_login(self.admin)
        self.teacher = Teacher.objects.create(
            full_name='مدرس', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.room = Room.objects.create(name='قاعة التوفر', capacity=20)
        self.group = Group.objects.create(
            group_name='مجموعة', teacher=self.teacher,
            schedule_day='Saturday', schedule_time=time(14, 0),
            standard_fee=Decimal('100'),
        )
        for day, start in [('Saturday', time(14, 0)), ('Wednesday', time(18, 0))]:
            GroupSchedule.objects.create(
                group=self.group, day_of_week=day, start_time=start, duration=120,
                room=self.room,
            )

    def _check(self, day, time_str):
        return self.client.post(
            reverse('teachers:api_room_availability'),
            data=json.dumps({
                'room_id': self.room.pk, 'day': day,
                'time': time_str, 'duration_minutes': 120,
            }),
            content_type='application/json',
        ).json()

    def test_conflict_detected_on_a_secondary_day(self):
        payload = self._check('Wednesday', '18:30')
        self.assertTrue(payload['success'])
        self.assertFalse(payload['available'])
        self.assertEqual(payload['conflicts'][0]['name'], 'مجموعة')

    def test_free_slot_is_reported_available(self):
        payload = self._check('Wednesday', '21:00')
        self.assertTrue(payload['available'])

    def test_bad_payload_does_not_leak_exception_text(self):
        response = self.client.post(
            reverse('teachers:api_room_availability'),
            data='not json', content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('صيغة', response.json()['error'])


class ListPaginationTest(TestCase):
    """PERF-15 — the list screens must not load the whole table."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='page_admin', password='TestPass123!', role='admin',
        )
        self.client.force_login(self.admin)
        for index in range(30):
            Teacher.objects.create(
                full_name=f'مدرس {index:02d}', phone=f'0100000{index:04d}',
                hire_date=date(2024, 1, 1),
            )

    def test_teacher_list_is_paginated(self):
        response = self.client.get(reverse('teachers:list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['teachers']), 25)
        self.assertEqual(response.context['total_count'], 30)

    def test_second_page_holds_the_rest(self):
        response = self.client.get(reverse('teachers:list'), {'page': 2})
        self.assertEqual(len(response.context['teachers']), 5)

    def test_invalid_page_falls_back_to_the_first(self):
        response = self.client.get(reverse('teachers:list'), {'page': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 1)


class GroupAdminConflictOptInTest(TestCase):
    """DATA-30 — no more deciding policy by grepping Arabic out of an exception."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite

        from .admin import GroupAdmin, GroupAdminForm

        self.GroupAdmin = GroupAdmin
        self.GroupAdminForm = GroupAdminForm
        self.site = AdminSite()
        self.teacher = Teacher.objects.create(
            full_name='مدرس', phone='0100', hire_date=date(2024, 1, 1),
        )
        self.room = Room.objects.create(name='قاعة الأدمن', capacity=10)
        self.existing = create_group_with_schedule(
            group_name='القائمة', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(9, 0),
            standard_fee=Decimal('100'),
        )

    def _data(self, **overrides):
        data = {
            'group_name': 'الجديدة',
            'teacher': self.teacher.pk,
            'room': self.room.pk,
            'schedule_day': 'Saturday',
            'schedule_time': '09:30',
            'duration_minutes': 120,
            'gender_type': 'mixed',
            'education_stage': '',
            'education_year': '',
            'standard_fee': '100',
            'center_percentage': '30',
            'sessions_per_month': 4,
            'is_active': True,
        }
        data.update(overrides)
        return data

    def test_conflict_blocks_the_form_without_the_opt_in(self):
        form = self.GroupAdminForm(self._data())
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_opt_in_saves_and_warns(self):
        form = self.GroupAdminForm(self._data(allow_schedule_conflict='on'))
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)

        warnings = []
        model_admin = self.GroupAdmin(Group, self.site)
        model_admin.message_user = (
            lambda request, message, level=None: warnings.append(message)
        )
        model_admin.save_model(object(), obj, form, change=False)

        self.assertIsNotNone(obj.pk)
        self.assertEqual(len(warnings), 1)
        self.assertIn('تداخل', warnings[0])

    def test_opt_in_does_not_bypass_the_stage_year_rule(self):
        form = self.GroupAdminForm(self._data(
            allow_schedule_conflict='on',
            education_stage='secondary',
            education_year='6',
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('education_year', form.errors)


class GroupDetailViewTest(TestCase):
    """
    teachers:group_detail — tightened from @login_required to
    @supervisor_required (a teacher account used to see every student's
    phone/payment data for any group), and now shows the students table +
    attendance grid.
    """

    def setUp(self):
        self.client = Client()
        self.supervisor = get_user_model().objects.create_user(
            username='grpdet_sup', password='TestPass123!', role='supervisor',
        )
        self.teacher_user = get_user_model().objects.create_user(
            username='grpdet_teacher', password='TestPass123!', role='teacher',
        )
        self.room = Room.objects.create(name='قاعة التفاصيل', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس التفاصيل', phone='01077770000',
            specialization='فيزياء', hire_date=date(2024, 1, 1),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة التفاصيل', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(10, 0),
            standard_fee=Decimal('150.00'),
        )
        self.student = Student.objects.create(
            student_code='GD001', full_name='طالب التفاصيل', gender='male',
            parent_phone='01077771111', student_phone='01077772222',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group, financial_status='normal', is_active=True,
        )
        self.url = reverse('teachers:group_detail', kwargs={'group_id': self.group.group_id})

    def test_teacher_role_forbidden(self):
        self.client.login(username='grpdet_teacher', password='TestPass123!')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_supervisor_sees_student_phone_and_payment_status(self):
        self.client.login(username='grpdet_sup', password='TestPass123!')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '01077772222')
        self.assertEqual(len(response.context['students_rows']), 1)
        self.assertEqual(response.context['students_rows'][0]['payment_status'], 'unpaid')

    def test_custom_date_range(self):
        self.client.login(username='grpdet_sup', password='TestPass123!')
        response = self.client.get(self.url, {'from': '2026-01-01', 'to': '2026-01-31'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['grid_from'].isoformat(), '2026-01-01')


class GroupRosterPrintTest(TestCase):
    """attendance:group_roster_print — printable attendance sheet."""

    def setUp(self):
        self.client = Client()
        self.supervisor = get_user_model().objects.create_user(
            username='roster_sup', password='TestPass123!', role='supervisor',
        )
        self.room = Room.objects.create(name='قاعة الكشف', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس الكشف', phone='01066660000',
            specialization='كيمياء', hire_date=date(2024, 1, 1),
        )
        self.group = create_group_with_schedule(
            group_name='مجموعة الكشف', teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(9, 0),
            standard_fee=Decimal('100.00'),
        )
        self.student = Student.objects.create(
            student_code='RP001', full_name='طالب الكشف', gender='male',
            parent_phone='01066661111',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group, financial_status='normal', is_active=True,
        )
        self.url = reverse('attendance:group_roster_print', kwargs={'group_id': self.group.group_id})

    def test_requires_supervisor(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 401))

    def test_renders_with_student_name(self):
        self.client.login(username='roster_sup', password='TestPass123!')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'طالب الكشف')
        self.assertContains(response, 'زائر / غير مسجَّل')
