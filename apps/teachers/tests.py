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
        from datetime import time
        
        # المجموعة الأولى: السبت 9:00
        Group.objects.create(
            group_name='مجموعة الصباح',
            teacher=self.teacher1,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(9, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # المجموعة الثانية: السبت 13:00 (نفس القاعة، نفس اليوم، لكن وقت مختلف بفاصل كافٍ)
        group2 = Group.objects.create(
            group_name='مجموعة الظهر',
            teacher=self.teacher2,
            room=self.room,
            schedule_day='Saturday',
            schedule_time=time(13, 0),  # وقت مختلف مع فاصل كافٍ
            session_duration=120,
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


class RoomScheduleServiceTest(TestCase):
    """
    Unit Tests لـ RoomScheduleService
    اختبار خدمة جدولة القاعات المتقدمة
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        from datetime import time
        
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

        self.room1 = Room.objects.create(name='قاعة A', capacity=30)
        self.room2 = Room.objects.create(name='قاعة B', capacity=25)

    def test_no_conflict_exact_time_match(self):
        """اختبار: كشف التعارض عند تطابق الوقت تماماً"""
        from .services import RoomScheduleService
        from datetime import time
        
        # إنشاء المجموعة الأولى: 10:00 - 12:00
        group1 = Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # فحص تعارض لنفس الوقت تماماً
        conflict = RoomScheduleService.check_room_conflict(
            room=self.room1,
            day='Sunday',
            start_time=time(10, 0),
            duration=120
        )

        self.assertIsNotNone(conflict)
        self.assertIn('conflict_group_name', conflict)
        self.assertEqual(conflict['conflict_group_name'], 'مجموعة 1')

    def test_conflict_overlapping_time_ranges(self):
        """اختبار: كشف التعارض عند تداخل النطاقات الزمنية"""
        from .services import RoomScheduleService
        from datetime import time
        
        # المجموعة الأولى: 10:00 - 12:00
        Group.objects.create(
            group_name='مجموعة الصباح',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # فحص تعارض: 11:00 - 13:00 (يتداخل مع 10:00 - 12:00)
        conflict = RoomScheduleService.check_room_conflict(
            room=self.room1,
            day='Sunday',
            start_time=time(11, 0),
            duration=120
        )

        self.assertIsNotNone(conflict)
        self.assertIn('message_ar', conflict)

    def test_conflict_with_buffer_time(self):
        """اختبار: فحص الفاصل الزمني (15 دقيقة) بين الحصص"""
        from .services import RoomScheduleService
        from datetime import time
        
        # المجموعة الأولى: 10:00 - 12:00
        Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # فحص: 12:00 - 14:00 (لا يوجد تعارض، فاصل 0 دقيقة)
        # لكن مع الفاصل الزمني 15 دقيقة، يجب أن يعتبر تعارضاً
        conflict = RoomScheduleService.check_room_conflict(
            room=self.room1,
            day='Sunday',
            start_time=time(12, 0),
            duration=120
        )

        # يجب أن يوجد تعارض بسبب الفاصل الزمني
        self.assertIsNotNone(conflict)

    def test_no_conflict_with_sufficient_gap(self):
        """اختبار: عدم وجود تعارض عند وجود فاصل كافٍ"""
        from .services import RoomScheduleService
        from datetime import time
        
        # المجموعة الأولى: 10:00 - 12:00
        Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # فحص: 12:30 - 14:30 (فاصل 30 دقيقة، أكبر من 15)
        conflict = RoomScheduleService.check_room_conflict(
            room=self.room1,
            day='Sunday',
            start_time=time(12, 30),
            duration=120
        )

        self.assertIsNone(conflict)

    def test_get_available_rooms(self):
        """اختبار: البحث عن القاعات المتاحة"""
        from .services import RoomScheduleService
        from datetime import time
        
        # حجز قاعة A في Sunday 10:00
        Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # البحث عن قاعات متاحة في Sunday 10:00
        available = RoomScheduleService.get_available_rooms(
            day='Sunday',
            start_time=time(10, 0),
            duration=120
        )

        # يجب أن تكون القائمة مرتبة: المتاحة أولاً ثم غير المتاحة
        self.assertEqual(len(available), 2)
        
        # نتحقق من وجود قاعة متاحة وقاعة غير متاحة
        available_rooms = [r for r in available if r['is_available']]
        unavailable_rooms = [r for r in available if not r['is_available']]
        
        self.assertEqual(len(available_rooms), 1)  # قاعة B متاحة
        self.assertEqual(len(unavailable_rooms), 1)  # قاعة A محجوزة

    def test_get_available_rooms_with_capacity_filter(self):
        """اختبار: البحث عن قاعات متاحة مع تصفية بالسعة"""
        from .services import RoomScheduleService
        from datetime import time
        
        # البحث عن قاعات بسعة 20 فأكثر
        available = RoomScheduleService.get_available_rooms(
            day='Sunday',
            start_time=time(10, 0),
            duration=120,
            min_capacity=20
        )

        # كلتا القاعتين متاحتان (السعة 25 و 30)
        self.assertTrue(all(r['is_available'] for r in available))

    def test_calculate_room_utilization(self):
        """اختبار: حساب نسبة استخدام القاعة"""
        from .services import RoomScheduleService
        from datetime import time
        
        # إنشاء 3 مجموعات في قاعة A في أيام مختلفة لتجنب التعارض
        days = ['Sunday', 'Monday', 'Tuesday']
        for i, day in enumerate(days):
            Group.objects.create(
                group_name=f'مجموعة {i+1}',
                teacher=self.teacher1,
                room=self.room1,
                schedule_day=day,
                schedule_time=time(10, 0),
                session_duration=120,
                standard_fee=200.00
            )

        utilization = RoomScheduleService.calculate_room_utilization(self.room1)

        self.assertIn('utilization_percentage', utilization)
        self.assertIn('session_count', utilization)
        self.assertEqual(utilization['session_count'], 3)

    def test_get_room_schedule(self):
        """اختبار: الحصول على جدول القاعة"""
        from .services import RoomScheduleService
        from datetime import time
        
        # إنشاء مجموعة
        Group.objects.create(
            group_name='مجموعة الأحد',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        schedule = RoomScheduleService.get_room_schedule(self.room1)

        self.assertIn('Sunday', schedule)
        self.assertEqual(len(schedule['Sunday']), 1)
        self.assertEqual(schedule['Sunday'][0]['group_name'], 'مجموعة الأحد')

    def test_exclude_group_id_in_conflict_check(self):
        """اختبار: استبعاد مجموعة معينة من فحص التعارض (للتحديث)"""
        from .services import RoomScheduleService
        from datetime import time
        
        # إنشاء مجموعة
        group = Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # فحص تعارض مع استبعاد المجموعة نفسها
        conflict = RoomScheduleService.check_room_conflict(
            room=self.room1,
            day='Sunday',
            start_time=time(10, 0),
            duration=120,
            exclude_group_id=group.group_id
        )

        # لا يجب أن يوجد تعارض لأننا است exclusion
        self.assertIsNone(conflict)

    def test_get_end_time_method(self):
        """اختبار: طريقة حساب وقت الانتهاء"""
        from datetime import time
        
        group = Group.objects.create(
            group_name='مجموعة اختبار',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        end_time = group.get_end_time()
        self.assertEqual(end_time.hour, 12)
        self.assertEqual(end_time.minute, 0)

    def test_get_time_range_display(self):
        """اختبار: عرض نطاق الوقت"""
        from datetime import time
        
        group = Group.objects.create(
            group_name='مجموعة اختبار',
            teacher=self.teacher1,
            room=self.room1,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        time_range = group.get_time_range_display()
        self.assertEqual(time_range, '10:00 - 12:00')


class GroupModelValidationTest(TestCase):
    """
    Unit Tests لـ Group Model Validation
    اختبار التحقق من صحة نموذج المجموعة
    """

    def setUp(self):
        """إعداد البيانات للاختبار"""
        self.teacher = Teacher.objects.create(
            full_name='محمد علي',
            email='teacher@test.com',
            phone='+201234567890',
            specialization='رياضيات',
            hire_date='2020-01-01'
        )

        self.room = Room.objects.create(name='قاعة A', capacity=30)

    def test_clean_method_detects_conflict(self):
        """اختبار: طريقة clean() تكتشف التعارضات"""
        from datetime import time
        from django.core.exceptions import ValidationError
        
        # إنشاء المجموعة الأولى
        Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # محاولة إنشاء مجموعة متعارضة
        group2 = Group(
            group_name='مجموعة 2',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(11, 0),  # يتداخل مع 10:00 - 12:00
            session_duration=120,
            standard_fee=200.00
        )

        # يجب أن يرفع ValidationError
        with self.assertRaises(ValidationError):
            group2.full_clean()

    def test_save_with_skip_validation(self):
        """اختبار: الحفظ مع تخطي التحقق"""
        from datetime import time
        
        # إنشاء المجموعة الأولى
        Group.objects.create(
            group_name='مجموعة 1',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )

        # حفظ مجموعة متعارضة مع تخطي التحقق
        group2 = Group(
            group_name='مجموعة 2',
            teacher=self.teacher,
            room=self.room,
            schedule_day='Sunday',
            schedule_time=time(10, 0),
            session_duration=120,
            standard_fee=200.00
        )
        group2.save(skip_validation=True)

        # يجب أن يتم الحفظ بنجاح
        self.assertIsNotNone(group2.pk)
