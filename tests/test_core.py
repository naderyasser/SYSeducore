"""
Soft Deletion & Data Integrity Tests.

Tests:
- Soft delete hides from default manager, visible in all_objects
- Restore brings back soft-deleted records
- PROTECT FK prevents permanent deletion of linked records
- hard_delete permanently removes records
- Recycle bin operations
"""
from datetime import date, time
from decimal import Decimal

from django.db import IntegrityError
from django.db.models import ProtectedError
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.students.models import Student, StudentGroupEnrollment
from apps.teachers.models import Teacher, Group, Room
from apps.attendance.models import Session, Attendance

User = get_user_model()


class TestSoftDeleteBasics(TestCase):
    """Test SoftDeleteModel core functionality."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_sd', password='Test123!', role='admin'
        )
        self.room = Room.objects.create(name='قاعة حذف', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس حذف', phone='01011110000',
            specialization='فيزياء', hire_date=date(2024, 1, 1),
        )

    def test_soft_delete_hides_from_default_manager(self):
        """Soft-deleted group must disappear from Group.objects.all()."""
        group = Group.objects.create(
            group_name='ستحذف',
            teacher=self.teacher, room=self.room,
            schedule_day='Saturday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('100.00'),
        )
        group_id = group.pk

        group.soft_delete(user=self.admin)

        # Must NOT appear in default manager
        self.assertFalse(Group.objects.filter(pk=group_id).exists())

    def test_soft_delete_visible_in_all_objects(self):
        """Soft-deleted group must be visible via Group.all_objects.dead()."""
        group = Group.objects.create(
            group_name='ستحذف 2',
            teacher=self.teacher, room=self.room,
            schedule_day='Sunday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('100.00'),
        )
        group_id = group.pk

        group.soft_delete(user=self.admin)

        # Must appear in all_objects
        self.assertTrue(Group.all_objects.filter(pk=group_id).exists())
        # Must appear in dead()
        self.assertTrue(Group.all_objects.dead().filter(pk=group_id).exists())
        # Must NOT appear in alive()
        self.assertFalse(Group.all_objects.alive().filter(pk=group_id).exists())

    def test_soft_delete_records_metadata(self):
        """Soft delete must record deleted_at timestamp and deleted_by user."""
        group = Group.objects.create(
            group_name='بيانات الحذف',
            teacher=self.teacher, room=self.room,
            schedule_day='Monday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('100.00'),
        )

        group.soft_delete(user=self.admin)
        group.refresh_from_db()

        self.assertIsNotNone(group.deleted_at)
        self.assertEqual(group.deleted_by, self.admin)
        self.assertTrue(group.is_deleted)

    def test_restore_brings_back(self):
        """Restoring a soft-deleted record should make it visible again."""
        student = Student.objects.create(
            student_code='DEL001', full_name='طالب محذوف',
            gender='male', parent_phone='01099990000',
            student_phone='01099991111',
        )
        student_id = student.pk

        student.soft_delete(user=self.admin)
        self.assertFalse(Student.objects.filter(pk=student_id).exists())

        # Restore
        student.restore()
        self.assertTrue(Student.objects.filter(pk=student_id).exists())

        student.refresh_from_db()
        self.assertIsNone(student.deleted_at)
        self.assertIsNone(student.deleted_by)
        self.assertFalse(student.is_deleted)

    def test_hard_delete_permanently_removes(self):
        """hard_delete() must permanently remove the record from database."""
        room = Room.objects.create(name='ستحذف نهائي', capacity=10)
        room_id = room.pk

        room.soft_delete(user=self.admin)
        Room.all_objects.dead().filter(pk=room_id).hard_delete()

        # Must not exist anywhere
        self.assertFalse(Room.all_objects.filter(pk=room_id).exists())


class TestProtectedForeignKeys(TestCase):
    """Test that PROTECT FK prevents deletion of linked records."""

    def setUp(self):
        self.room = Room.objects.create(name='قاعة حماية', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس محمي', phone='01022220000',
            specialization='كيمياء', hire_date=date(2024, 1, 1),
        )
        self.group = Group.objects.create(
            group_name='مجموعة محمية',
            teacher=self.teacher, room=self.room,
            schedule_day='Wednesday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('100.00'),
        )

    def test_cannot_hard_delete_teacher_with_groups(self):
        """Permanently deleting a teacher that has groups — must raise ProtectedError."""
        with self.assertRaises(ProtectedError):
            self.teacher.delete()

    def test_cannot_hard_delete_room_with_groups(self):
        """Permanently deleting a room that has groups — must raise ProtectedError."""
        with self.assertRaises(ProtectedError):
            self.room.delete()

    def test_cannot_delete_student_with_attendance(self):
        """Permanently deleting a student that has attendance — must raise ProtectedError."""
        student = Student.objects.create(
            student_code='PROT01', full_name='طالب محمي',
            gender='male', parent_phone='01033330000',
            student_phone='01033331111',
        )
        session = Session.objects.create(
            group=self.group, session_date=timezone.now().date()
        )
        Attendance.objects.create(
            student=student, session=session,
            scan_time=timezone.now(), status='present',
        )

        with self.assertRaises(ProtectedError):
            student.delete()

    def test_soft_delete_teacher_with_groups_works(self):
        """Soft-deleting a teacher with groups should work fine (not hard delete)."""
        admin = User.objects.create_user(
            username='admin_prot', password='Test123!', role='admin'
        )
        # Should NOT raise
        self.teacher.soft_delete(user=admin)
        self.assertTrue(self.teacher.is_deleted)


class TestSoftDeleteStudent(TestCase):
    """Test student-specific soft delete scenarios."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_st', password='Test123!', role='admin'
        )
        self.room = Room.objects.create(name='قاعة طالب', capacity=20)
        self.teacher = Teacher.objects.create(
            full_name='مدرس طالب', phone='01044440000',
            specialization='رياضيات', hire_date=date(2024, 1, 1),
        )
        self.group = Group.objects.create(
            group_name='مجموعة طالب',
            teacher=self.teacher, room=self.room,
            schedule_day='Thursday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('200.00'),
        )
        self.student = Student.objects.create(
            student_code='SFT001', full_name='طالب سيحذف',
            gender='male', parent_phone='01044441111',
            student_phone='01044442222',
        )
        StudentGroupEnrollment.objects.create(
            student=self.student, group=self.group,
            financial_status='normal', is_active=True,
        )

    def test_soft_deleted_student_enrollment_still_queryable(self):
        """Soft-deleting a student — enrollment records should still exist."""
        self.student.soft_delete(user=self.admin)

        # Enrollment still exists (not cascaded)
        enrollment = StudentGroupEnrollment.objects.filter(
            student=self.student, group=self.group
        ).first()
        self.assertIsNotNone(enrollment)

    def test_multiple_soft_delete_restore_cycles(self):
        """Delete → restore → delete → restore should work correctly."""
        for _ in range(3):
            self.student.soft_delete(user=self.admin)
            self.assertTrue(self.student.is_deleted)
            self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())

            self.student.restore()
            self.assertFalse(self.student.is_deleted)
            self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())
