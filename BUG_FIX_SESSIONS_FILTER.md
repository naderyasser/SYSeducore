# Bug Fix: Deleted Groups Still Visible in Bookings

## المشكلة
المجموعات المحذوفة من `/teachers/groups/` كانت لا تزال تظهر في `/teachers/bookings/`

## السبب الجذري
استعلامات `Session.objects.filter()` لم تكن تفلتر المجموعات غير النشطة (`is_active=False`)

## الملفات المعدلة

### 1. `apps/teachers/views.py`
**السطر 35:** Teacher detail - upcoming sessions
```python
# قبل
upcoming_sessions = Session.objects.filter(
    group__teacher=teacher,
    session_date__gte=today,
    session_date__lte=next_week,
    is_cancelled=False
)

# بعد
upcoming_sessions = Session.objects.filter(
    group__teacher=teacher,
    group__is_active=True,  # ✅ Added
    session_date__gte=today,
    session_date__lte=next_week,
    is_cancelled=False
)
```

**السطر 451:** Bookings search - upcoming sessions
```python
# قبل
upcoming_sessions = Session.objects.filter(
    session_date__gte=today,
    session_date__lte=next_week,
    is_cancelled=False
)

# بعد
upcoming_sessions = Session.objects.filter(
    session_date__gte=today,
    session_date__lte=next_week,
    is_cancelled=False,
    group__is_active=True  # ✅ Added
)
```

### 2. `apps/attendance/views.py`
**السطر 145:** Today stats - session count
```python
# قبل
today_sessions = Session.objects.filter(
    session_date=today,
    is_cancelled=False
).count()

# بعد
today_sessions = Session.objects.filter(
    session_date=today,
    is_cancelled=False,
    group__is_active=True  # ✅ Added
).count()
```

### 3. `apps/reports/views.py`
**السطر 108:** Dashboard - today's sessions
```python
# قبل
today_sessions = Session.objects.filter(session_date=today)

# بعد
today_sessions = Session.objects.filter(session_date=today, group__is_active=True)
```

### 4. `apps/notifications/tasks.py`
**السطر 17:** Notification task - session notifications
```python
# قبل
sessions = Session.objects.filter(
    session_date=now.date(),
    notification_sent=False,
    is_cancelled=False
)

# بعد
sessions = Session.objects.filter(
    session_date=now.date(),
    notification_sent=False,
    is_cancelled=False,
    group__is_active=True  # ✅ Added
)
```

## التحقق من الإصلاح

### قبل الإصلاح:
```
Total sessions: 3
Upcoming sessions (without filter): 3  ❌ يعرض المحذوفة
Upcoming sessions (with filter): 1     ✅ الصحيح
```

### بعد الإصلاح:
```
Upcoming sessions: 1  ✅ فقط المجموعات النشطة
```

### Sessions مع مجموعات محذوفة (مخفية الآن):
- Rose Benson on 2026-02-10
- TEST - Current Time Group on 2026-02-10

## التأثير

### الصفحات المتأثرة:
1. ✅ `/teachers/bookings/` - Bookings search page
2. ✅ `/teachers/{id}/` - Teacher detail page
3. ✅ `/attendance/api/today-stats/` - Today's stats API
4. ✅ `/reports/` - Dashboard reports
5. ✅ Background notifications task

### النتيجة:
- المجموعات المحذوفة (`is_active=False`) لن تظهر في أي مكان
- الحصص (Sessions) المرتبطة بمجموعات محذوفة مخفية
- الإحصائيات تعكس فقط المجموعات النشطة

## الاختبار

### خطوات التحقق:
1. اذهب إلى `/teachers/groups/`
2. احذف مجموعة (تصبح `is_active=False`)
3. اذهب إلى `/teachers/bookings/`
4. ✅ المجموعة المحذوفة لن تظهر

### قاعدة البيانات:
```sql
-- Active groups (visible)
SELECT COUNT(*) FROM groups WHERE is_active = 1;  -- 1

-- Inactive groups (hidden)
SELECT COUNT(*) FROM groups WHERE is_active = 0;  -- 3
```

## الخلاصة

✅ **تم الإصلاح** - جميع استعلامات Session الآن تفلتر المجموعات غير النشطة

**الملفات المعدلة:** 4
**الأسطر المعدلة:** 5
**الخدمة:** تم إعادة التشغيل

المجموعات المحذوفة الآن مخفية تماماً من جميع الصفحات والتقارير.
