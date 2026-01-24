"""
Unit Tests for Teachers App - Educore V2
اختبار Room Model + Conflict Validation
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from .models import Teacher, Room, Group


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
        """اختبار: إنشاء مجموعة مع قاعة"""
        group = Group.objects.create(
            group_name='مجموعة السبت',
            teacher=self.teacher1,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        self.assertEqual(group.room, self.room)
        self.assertEqual(group.schedule_day, 'Saturday')

    def test_conflict_same_room_same_time(self):
        """اختبار: منع إنشاء مجموعتين في نفس القاعة + نفس اليوم + نفس الوقت"""
        # إنشاء المجموعة الأولى
        Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher1,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        # محاولة إنشاء مجموعة ثانية بنفس القاعة والوقت
        with self.assertRaises((ValidationError, IntegrityError)):
            group2 = Group(
                group_name='مجموعة 2',
                teacher=self.teacher2,
                room=self.room,
                schedule_day='Saturday',  # نفس اليوم
                schedule_time='09:00',    # نفس الوقت
                standard_fee=200.00
            )
            group2.save()  # سيفشل بسبب الـ validation

    def test_no_conflict_different_day(self):
        """اختبار: السماح بنفس القاعة والوقت لكن يوم مختلف"""
        # المجموعة الأولى: السبت 9:00
        Group.objects.create(
            group_name='مجموعة السبت',
            teacher=self.teacher1,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        # المجموعة الثانية: الأحد 9:00 (نفس القاعة، نفس الوقت، لكن يوم مختلف)
        group2 = Group.objects.create(
            group_name='مجموعة الأحد',
            teacher=self.teacher2,
            room=self.room,
            schedule_day='Sunday',  # يوم مختلف
            schedule_time='09:00',
            standard_fee=200.00
        )

        self.assertIsNotNone(group2.pk)  # تم الحفظ بنجاح

    def test_no_conflict_different_time(self):
        """اختبار: السماح بنفس القاعة واليوم لكن وقت مختلف"""
        # المجموعة الأولى: السبت 9:00
        Group.objects.create(
            group_name='مجموعة الصباح',
            teacher=self.teacher1,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        # المجموعة الثانية: السبت 11:00 (نفس القاعة، نفس اليوم، لكن وقت مختلف)
        group2 = Group.objects.create(
            group_name='مجموعة الظهر',
            teacher=self.teacher2,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='11:00',  # وقت مختلف
            standard_fee=200.00
        )

        self.assertIsNotNone(group2.pk)  # تم الحفظ بنجاح

    def test_no_conflict_no_room(self):
        """اختبار: السماح بمجموعات بدون قاعة"""
        # مجموعة 1 بدون قاعة
        group1 = Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher1,
            room=None,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        # مجموعة 2 بدون قاعة (نفس اليوم والوقت)
        group2 = Group.objects.create(
            group_name='مجموعة 2',
            teacher=self.teacher2,
            room=None,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        # يجب السماح لأنه لا توجد قاعة
        self.assertIsNotNone(group1.pk)
        self.assertIsNotNone(group2.pk)

    def test_group_without_grace_period(self):
        """اختبار: المجموعة لا تحتوي على grace_period (النظام الثابت)"""
        group = Group.objects.create(
            group_name='مجموعة اختبار',
            teacher=self.teacher1,
            room=self.room,
            schedule_day='Saturday',
            schedule_time='09:00',
            standard_fee=200.00
        )

        # التأكد أن grace_period غير موجود
        self.assertFalse(hasattr(group, 'grace_period'))
