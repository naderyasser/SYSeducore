"""
Educational Hierarchy & Room Conflict Tests.

Tests:
- Room time-slot overlap detection (Smart Overlap Check)
- Education stage/year validation on Group and Student
- Group creation with valid/invalid combos
"""
from datetime import date, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.students.models import Student
from apps.teachers.models import Teacher, Group, Room, Subject


class RoomConflictTestMixin:
    """Shared setup for room conflict tests."""

    def setUp(self):
        self.room = Room.objects.create(name='قاعة تعارض', capacity=30)
        self.teacher1 = Teacher.objects.create(
            full_name='مدرس أ', phone='01011111111',
            specialization='رياضيات', hire_date=date(2024, 1, 1),
        )
        self.teacher2 = Teacher.objects.create(
            full_name='مدرس ب', phone='01022222222',
            specialization='علوم', hire_date=date(2024, 1, 1),
        )

        # Existing group: Saturday 14:00-16:00 (120 min)
        self.existing_group = Group.objects.create(
            group_name='المجموعة الأصلية',
            teacher=self.teacher1, room=self.room,
            schedule_day='Saturday', schedule_time=time(14, 0),
            duration_minutes=120, standard_fee=Decimal('200.00'),
        )


class TestRoomOverlapDetection(RoomConflictTestMixin, TestCase):
    """Test room scheduling conflict validation."""

    def test_overlap_same_room_same_day_blocked(self):
        """Overlapping time in same room, same day — must raise ValidationError."""
        # Try: Saturday 15:00-17:00 (overlaps with 14:00-16:00)
        conflicting = Group(
            group_name='متعارض',
            teacher=self.teacher2, room=self.room,
            schedule_day='Saturday', schedule_time=time(15, 0),
            duration_minutes=120, standard_fee=Decimal('150.00'),
        )
        with self.assertRaises(ValidationError):
            conflicting.full_clean()

    def test_overlap_start_during_existing_blocked(self):
        """New group starts during existing — must be blocked."""
        # Try: Saturday 14:30 (starts during 14:00-16:00)
        conflicting = Group(
            group_name='يبدأ أثناء',
            teacher=self.teacher2, room=self.room,
            schedule_day='Saturday', schedule_time=time(14, 30),
            duration_minutes=60, standard_fee=Decimal('150.00'),
        )
        with self.assertRaises(ValidationError):
            conflicting.full_clean()

    def test_exact_boundary_allowed(self):
        """New group starts exactly when existing ends — should be ALLOWED."""
        # Existing: 14:00-16:00, New: 16:00-18:00 (exact boundary)
        non_conflicting = Group(
            group_name='بعد مباشرة',
            teacher=self.teacher2, room=self.room,
            schedule_day='Saturday', schedule_time=time(16, 0),
            duration_minutes=120, standard_fee=Decimal('150.00'),
        )
        # Should NOT raise
        non_conflicting.full_clean()

    def test_before_existing_allowed(self):
        """New group ends before existing starts — should be ALLOWED."""
        # New: 11:00-13:00, Existing: 14:00-16:00
        non_conflicting = Group(
            group_name='قبل الأصلية',
            teacher=self.teacher2, room=self.room,
            schedule_day='Saturday', schedule_time=time(11, 0),
            duration_minutes=120, standard_fee=Decimal('150.00'),
        )
        non_conflicting.full_clean()

    def test_different_day_allowed(self):
        """Same room, same time, different day — should be ALLOWED."""
        non_conflicting = Group(
            group_name='يوم مختلف',
            teacher=self.teacher2, room=self.room,
            schedule_day='Sunday', schedule_time=time(14, 0),
            duration_minutes=120, standard_fee=Decimal('150.00'),
        )
        non_conflicting.full_clean()

    def test_different_room_allowed(self):
        """Different room, same day, overlapping time — should be ALLOWED."""
        room2 = Room.objects.create(name='قاعة أخرى', capacity=20)
        non_conflicting = Group(
            group_name='قاعة مختلفة',
            teacher=self.teacher2, room=room2,
            schedule_day='Saturday', schedule_time=time(14, 0),
            duration_minutes=120, standard_fee=Decimal('150.00'),
        )
        non_conflicting.full_clean()

    def test_complete_enclosure_blocked(self):
        """New group completely inside existing time slot — must be blocked."""
        # Existing: 14:00-16:00, New: 14:30-15:30
        conflicting = Group(
            group_name='داخل الوقت',
            teacher=self.teacher2, room=self.room,
            schedule_day='Saturday', schedule_time=time(14, 30),
            duration_minutes=60, standard_fee=Decimal('150.00'),
        )
        with self.assertRaises(ValidationError):
            conflicting.full_clean()

    def test_no_room_skips_validation(self):
        """Group with no room assigned — should skip room overlap check."""
        group = Group(
            group_name='بدون قاعة',
            teacher=self.teacher2, room=None,
            schedule_day='Saturday', schedule_time=time(14, 0),
            duration_minutes=120, standard_fee=Decimal('150.00'),
        )
        # Should NOT raise
        group.full_clean()


class TestEducationStageValidation(TestCase):
    """Test education stage/year combo validation."""

    def setUp(self):
        self.room = Room.objects.create(name='قاعة مراحل', capacity=30)
        self.teacher = Teacher.objects.create(
            full_name='مدرس مراحل', phone='01033333333',
            specialization='عربي', hire_date=date(2024, 1, 1),
        )

    # ---- Group Stage/Year Tests ----

    def test_primary_year_6_valid(self):
        """Primary stage, year 6 — valid combo."""
        group = Group(
            group_name='ابتدائي سادس',
            teacher=self.teacher, room=self.room,
            schedule_day='Monday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('150.00'),
            education_stage='primary', education_year='6',
        )
        group.full_clean()  # Should NOT raise

    def test_primary_year_invalid_blocked(self):
        """Primary stage, year > 6 — wait, we only have years 1-6, so test prep with year 4."""
        pass  # Covered by next test

    def test_preparatory_year_4_invalid(self):
        """Preparatory stage, year 4 — invalid, must raise ValidationError."""
        group = Group(
            group_name='إعدادي رابع',
            teacher=self.teacher, room=self.room,
            schedule_day='Monday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('150.00'),
            education_stage='preparatory', education_year='4',
        )
        with self.assertRaises(ValidationError) as ctx:
            group.full_clean()
        self.assertIn('education_year', ctx.exception.message_dict)

    def test_secondary_year_3_valid(self):
        """Secondary stage, year 3 — valid combo."""
        group = Group(
            group_name='ثانوي ثالث',
            teacher=self.teacher, room=self.room,
            schedule_day='Monday', schedule_time=time(12, 0),
            duration_minutes=90, standard_fee=Decimal('150.00'),
            education_stage='secondary', education_year='3',
        )
        group.full_clean()  # Should NOT raise

    def test_secondary_year_5_invalid(self):
        """Secondary stage, year 5 — invalid, must raise ValidationError."""
        group = Group(
            group_name='ثانوي خامس',
            teacher=self.teacher, room=self.room,
            schedule_day='Monday', schedule_time=time(14, 0),
            duration_minutes=90, standard_fee=Decimal('150.00'),
            education_stage='secondary', education_year='5',
        )
        with self.assertRaises(ValidationError):
            group.full_clean()

    def test_no_stage_any_year_valid(self):
        """No stage set — any year should be valid (optional fields)."""
        group = Group(
            group_name='بدون مرحلة',
            teacher=self.teacher, room=self.room,
            schedule_day='Tuesday', schedule_time=time(10, 0),
            duration_minutes=90, standard_fee=Decimal('150.00'),
            education_stage='', education_year='5',
        )
        group.full_clean()  # Should NOT raise

    # ---- Student Stage/Year Tests ----

    def test_student_primary_year_6_valid(self):
        """Student: primary, year 6 — valid."""
        student = Student(
            student_code='STG001', full_name='طالب ابتدائي',
            gender='male', parent_phone='01044444444',
            student_phone='01055555555',
            education_stage='primary', education_year='6',
        )
        student.full_clean()  # Should NOT raise

    def test_student_preparatory_year_5_invalid(self):
        """Student: preparatory, year 5 — invalid, must raise ValidationError."""
        student = Student(
            student_code='STG002', full_name='طالب إعدادي',
            gender='male', parent_phone='01044444444',
            student_phone='01055555555',
            education_stage='preparatory', education_year='5',
        )
        with self.assertRaises(ValidationError) as ctx:
            student.full_clean()
        self.assertIn('education_year', ctx.exception.message_dict)

    def test_student_secondary_year_4_invalid(self):
        """Student: secondary, year 4 — invalid."""
        student = Student(
            student_code='STG003', full_name='طالب ثانوي',
            gender='female', parent_phone='01044444444',
            student_phone='01055555555',
            education_stage='secondary', education_year='4',
        )
        with self.assertRaises(ValidationError):
            student.full_clean()
