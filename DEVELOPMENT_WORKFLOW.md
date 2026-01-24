# 📋 Development Workflow - Educore System

## نظرة عامة على الـ Workflow

هذا المستند يشرح كيفية عمل سير التطوير (Development Workflow) في نظام Educore من البداية للنهاية.

---

## 🔄 الـ Workflow الأساسي (لكل Feature جديدة)

```
┌─────────────────────────────────────────────────────────────┐
│  1️⃣ استلام الطلب (Feature Request)                        │
│     • فهم المتطلبات                                        │
│     • تحليل التأثير على النظام                            │
│     • تحديد الملفات التي ستتأثر                           │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  2️⃣ التخطيط (Planning)                                     │
│     • رسم خطة التنفيذ                                      │
│     • تحديد الخطوات المطلوبة                              │
│     • استخدام TodoWrite لتتبع المهام                      │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  3️⃣ التنفيذ (Implementation)                                │
│     • كتابة الـ Models (إن وُجد)                          │
│     • كتابة الـ Services/Logic                             │
│     • كتابة الـ Views/APIs                                 │
│     • تحديث الـ Admin Panels                               │
│     • تحديث الـ Forms                                      │
│     • إنشاء/تحديث الـ URLs                                │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  4️⃣ كتابة Unit Tests                                       │
│     • إنشاء/تحديث ملف tests.py                            │
│     • اختبار جميع الحالات (Success + Failure)             │
│     • اختبار Edge Cases                                    │
│     • اختبار الـ Validation                                │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  5️⃣ تشغيل الـ Tests                                        │
│     • تشغيل: python manage.py test                        │
│     • التأكد من نجاح جميع الـ Tests                        │
│     • إصلاح أي فشل في الـ Tests                           │
│     • إعادة التشغيل حتى النجاح الكامل                     │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  6️⃣ Git Commit                                              │
│     • git add <files>                                      │
│     • git commit -m "message"                              │
│     • رسالة واضحة توضح التغييرات                          │
│     • Co-Authored-By: Claude Sonnet 4.5                    │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
┌─────────────────────────────────────────────────────────────┐
│  7️⃣ Documentation (اختياري)                                │
│     • كتابة/تحديث الـ README                               │
│     • كتابة الـ API Documentation                          │
│     • كتابة الـ Upgrade Guides                             │
└─────────────────────────────────────────────────────────────┘
                            ⬇️
                        ✅ انتهى!
```

---

## 📝 مثال عملي: Educore V2 Upgrade

دعنا نستعرض كيف تم تطبيق الـ Workflow على تحديث Educore V2:

### 1️⃣ استلام الطلب

**الطلب:**
- تغيير من barcode → student_code
- إضافة Room model مع منع التعارض
- تطبيق قاعدة 10 دقائق صارمة
- إزالة grace_period

**التحليل:**
- سيؤثر على: Models, Services, Admin, Forms, Tests
- يحتاج: Migrations جديدة
- يحتاج: تحديث شامل للـ business logic

### 2️⃣ التخطيط

تم إنشاء Todo List:
```
✅ تغيير Student Model (barcode → student_code)
✅ إنشاء Room Model + Validation
✅ تحديث Group Model (room + حذف grace_period)
✅ إعادة كتابة AttendanceService
✅ تحديث Admin Panels
✅ تحديث Forms
✅ كتابة Unit Tests
✅ تشغيل Tests
✅ Git Commit
✅ كتابة Documentation
```

### 3️⃣ التنفيذ

#### A. Models ([apps/students/models.py](apps/students/models.py))
```python
# تغيير
barcode = models.CharField(max_length=50, unique=True)
# إلى
student_code = models.CharField(max_length=10, unique=True)
```

#### B. Room Model ([apps/teachers/models.py](apps/teachers/models.py))
```python
class Room(models.Model):
    room_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    capacity = models.PositiveIntegerField()
```

#### C. Conflict Validation ([apps/teachers/models.py](apps/teachers/models.py))
```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['room', 'schedule_day', 'schedule_time'],
            name='unique_room_schedule'
        )
    ]
```

#### D. AttendanceService ([apps/attendance/services.py](apps/attendance/services.py))
```python
@staticmethod
def process_scan(student_code, supervisor):
    # الخطوة 1: التعريف
    student = Student.objects.get(student_code=student_code)

    # الخطوة 2: مطابقة الجدول
    # ...

    # الخطوة 3: قاعدة الـ 10 دقائق
    time_check = AttendanceService.check_strict_time(...)

    # الخطوة 4: الفحص المالي
    financial_check = AttendanceService.check_financial_status(...)
```

### 4️⃣ كتابة Unit Tests

#### [apps/students/tests.py](apps/students/tests.py) - 9 tests
- ✅ test_create_student_with_student_code
- ✅ test_student_code_is_unique
- ✅ test_student_code_max_length
- ✅ test_student_str_representation
- ✅ test_create_enrollment_normal_status
- ✅ test_create_enrollment_exempt_status
- ✅ test_create_enrollment_symbolic_status
- ✅ test_unique_student_group_constraint
- ✅ test_get_monthly_fee_for_group_normal

#### [apps/teachers/tests.py](apps/teachers/tests.py) - 9 tests
- ✅ test_create_room
- ✅ test_room_name_is_unique
- ✅ test_room_str_representation
- ✅ test_create_group_with_room
- ✅ test_group_without_grace_period
- ✅ test_conflict_same_room_same_time
- ✅ test_no_conflict_different_day
- ✅ test_no_conflict_different_time
- ✅ test_no_conflict_no_room

#### [apps/attendance/tests.py](apps/attendance/tests.py) - 16 tests
- ✅ test_check_strict_time_on_time
- ✅ test_check_strict_time_5_minutes_late
- ✅ test_check_strict_time_exactly_10_minutes
- ✅ test_check_strict_time_11_minutes_late_block
- ✅ test_check_strict_time_15_minutes_late_block
- ✅ test_check_strict_time_too_early
- ✅ test_financial_check_exempt_always_allowed
- ✅ test_financial_check_first_month_no_payment
- ✅ test_financial_check_first_month_with_payment
- ✅ test_financial_check_subsequent_month_first_session
- ✅ test_financial_check_subsequent_month_third_session_blocked
- ✅ test_is_student_first_month_in_group_true
- ✅ test_is_student_first_month_in_group_false
- ✅ test_get_current_day_name
- ✅ test_process_scan_invalid_student_code
- ✅ test_process_scan_no_class_today

**إجمالي: 34 test**

### 5️⃣ تشغيل الـ Tests

```bash
python manage.py test apps.students apps.teachers apps.attendance --verbosity=2
```

**النتيجة:**
```
Ran 34 tests in 37.172s
OK
```

**ملاحظة:** واجهنا 3 فشل في البداية بسبب scan_time، تم إصلاحها بتحديد scan_time بشكل صريح في الـ tests.

### 6️⃣ Git Commit

```bash
git add apps/students/ apps/teachers/ apps/attendance/ config/ *.md
git commit -m "Educore V2: Complete system upgrade with unit tests"
```

**الرسالة شملت:**
- وصف المتطلبات الأربعة الرئيسية
- قائمة بجميع التغييرات
- ذكر الـ Tests (34 tests passing)
- Co-Authored-By: Claude

### 7️⃣ Documentation

تم إنشاء 3 ملفات documentation:
1. **[EDUCORE_V2_SYSTEM_UPGRADE.md](EDUCORE_V2_SYSTEM_UPGRADE.md)** - دليل التحديث الشامل
2. **[ADMIN_PERMISSIONS_GUIDE.md](ADMIN_PERMISSIONS_GUIDE.md)** - دليل صلاحيات الأدمن
3. **[DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md)** (هذا الملف) - شرح الـ Workflow

---

## 🎯 Best Practices

### 1. عند كتابة Tests:
- ✅ اختبار جميع الحالات (Success + Failure)
- ✅ اختبار الـ Validation
- ✅ اختبار الـ Edge Cases
- ✅ استخدام أسماء واضحة للـ tests
- ✅ إضافة docstrings توضيحية

### 2. عند عمل Commit:
- ✅ رسالة واضحة ومفصّلة
- ✅ ذكر جميع التغييرات الرئيسية
- ✅ إضافة Co-Authored-By إذا كان مع Claude
- ✅ استخدام HEREDOC للرسائل الطويلة

### 3. عند كتابة Code:
- ✅ اتباع DRY (Don't Repeat Yourself)
- ✅ استخدام Service Layer للـ business logic
- ✅ فصل الـ concerns (Model / Service / View)
- ✅ كتابة docstrings واضحة
- ✅ استخدام Type Hints (اختياري في Django)

### 4. عند كتابة Documentation:
- ✅ شرح "لماذا" وليس فقط "ماذا"
- ✅ إضافة أمثلة عملية
- ✅ ذكر التحذيرات المهمة (⚠️)
- ✅ استخدام Markdown بشكل صحيح

---

## 🔍 كيفية اختبار Feature جديدة

### خطوات الاختبار اليدوي:

1. **اختبار الـ Admin Panel:**
   ```bash
   python manage.py runserver
   # زيارة http://localhost:8000/admin/
   ```

2. **اختبار الـ API:**
   ```bash
   curl -X POST http://localhost:8000/attendance/api/process-code/ \
     -H "Content-Type: application/json" \
     -d '{"student_code": "1001"}'
   ```

3. **اختبار الـ Migrations:**
   ```bash
   python manage.py makemigrations --dry-run
   python manage.py migrate --plan
   python manage.py migrate
   ```

4. **اختبار الـ Tests:**
   ```bash
   python manage.py test
   python manage.py test apps.students
   python manage.py test apps.students.tests.StudentModelTest
   ```

---

## 🚨 Common Issues وكيفية حلّها

### 1. Migrations Conflicts
```bash
# حذف الـ migrations القديمة (احتياطياً فقط!)
python manage.py migrate <app_name> zero
# إنشاء migrations جديدة
python manage.py makemigrations
python manage.py migrate
```

### 2. Tests Failing
```bash
# تشغيل test واحد فقط
python manage.py test apps.students.tests.StudentModelTest.test_student_code_is_unique

# تشغيل مع verbosity عالي
python manage.py test --verbosity=3

# الاحتفاظ بقاعدة بيانات الاختبار للفحص
python manage.py test --keepdb
```

### 3. Import Errors
```bash
# التأكد من تثبيت المكتبات
pip install -r requirements.txt

# التأكد من الـ INSTALLED_APPS في settings.py
```

---

## 📊 الملفات الرئيسية في المشروع

```
EDU_SYS/
├── apps/
│   ├── students/
│   │   ├── models.py           ← Student, StudentGroupEnrollment
│   │   ├── admin.py            ← Admin panel
│   │   ├── forms.py            ← StudentForm
│   │   ├── tests.py            ← 9 tests
│   │   └── migrations/         ← Database migrations
│   │
│   ├── teachers/
│   │   ├── models.py           ← Teacher, Room, Group
│   │   ├── admin.py            ← RoomAdmin, GroupAdmin
│   │   ├── tests.py            ← 9 tests
│   │   └── migrations/
│   │
│   ├── attendance/
│   │   ├── models.py           ← Session, Attendance
│   │   ├── services.py         ← AttendanceService (4-step logic)
│   │   ├── views.py            ← process_student_code API
│   │   ├── admin.py            ← SessionAdmin, AttendanceAdmin
│   │   ├── tests.py            ← 16 tests
│   │   └── migrations/
│   │
│   ├── payments/
│   │   └── models.py           ← Payment
│   │
│   └── accounts/
│       └── models.py           ← User
│
├── config/
│   ├── settings.py             ← إعدادات Django
│   ├── urls.py                 ← URLs الرئيسية
│   └── __init__.py             ← Celery setup
│
├── EDUCORE_V2_SYSTEM_UPGRADE.md     ← دليل التحديث
├── ADMIN_PERMISSIONS_GUIDE.md       ← دليل صلاحيات Admin
├── DEVELOPMENT_WORKFLOW.md          ← هذا الملف
├── manage.py
└── requirements.txt
```

---

## 🎓 الخلاصة

### الـ Workflow باختصار:
```
طلب → تخطيط → تنفيذ → tests → تشغيل → commit → documentation
```

### النقاط الأساسية:
1. ✅ **دائماً** اكتب tests قبل الـ commit
2. ✅ **تأكد** من نجاح جميع الـ tests
3. ✅ **اكتب** commit message واضحة
4. ✅ **استخدم** TodoWrite لتتبع التقدم
5. ✅ **وثّق** التغييرات المهمة

---

## 📞 المساعدة

إذا واجهت أي مشكلة:
1. راجع هذا الملف أولاً
2. راجع الـ Tests لفهم الـ expected behavior
3. راجع الـ documentation files
4. استخدم `python manage.py shell` للتجربة

---

**تاريخ الإنشاء:** 2026-01-24
**النسخة:** 1.0
**الكاتب:** Claude Sonnet 4.5
