# دليل تكامل إشعارات WhatsApp
# WhatsApp Notification Integration Guide

## 📋 جدول المحتويات / Table of Contents

1. [نظرة عامة](#نظرة-عامة)
2. [سيناريوهات الإشعارات](#سيناريوهات-الإشعارات)
3. [التكوين والإعداد](#التكوين-والإعداد)
4. [دليل النشر](#دليل-النشر)
5. [دليل الاختبار](#دليل-الاختبار)
6. [استكشاف الأخطاء](#استكشاف-الأخطاء)

---

## نظرة عامة / Overview

### المكونات الرئيسية / Main Components

```
apps/notifications/
├── models.py              # NotificationTemplate, NotificationPreference, NotificationLog, NotificationCost
├── services.py            # WhatsAppService, TemplateService, NotificationService
├── tasks.py               # Celery tasks for async notifications
├── admin.py               # Admin interface for templates and logs
├── views.py               # Parent preferences, stats dashboard
└── migrations/
    └── 0002_add_template_and_preferences.py
```

### سير العمل / Workflow

```
┌─────────────────┐
│  Student Scan   │
│     QR Code     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│   AttendanceService     │
│   - Time Check          │
│   - Financial Check     │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│   Celery Task (async)   │
│   - Send Notification   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│   WhatsAppService       │
│   - UltraMsg API        │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│   Parent Receives       │
│   WhatsApp Message      │
└─────────────────────────┘
```

---

## سيناريوهات الإشعارات / Notification Scenarios

### 1. 🟢 حضور ناجح / Successful Attendance

**الزناد / Trigger:** الطالب يمسح QR، status = present، allow_entry = true

**القالب / Template:**
```
السلام عليكم
وصل الطالب/ة {student_name} إلى الحصة
المادة: {group_name}
التوقيت: {scan_time}
الحالة: حضور ✅
```

**الكود / Code:**
```python
# apps/attendance/services.py
AttendanceService._trigger_attendance_success_notification(
    student=student,
    group=group,
    scan_time=current_time
)
```

---

### 2. 🔴 منع التأخير / Late Block

**الزناد / Trigger:** الطالب يمسح QR، status = late_blocked، allow_entry = false

**القالب / Template:**
```
تنبيه ⚠️
تم منع الطالب/ة {student_name} من الدخول
السبب: تجاوز مهلة التأخير (10 دقائق)
الحصة: {group_name}
الوقت المحدد: {scheduled_time}
وقت الوصول: {scan_time}
الرجاء الالتزام بالمواعيد 🕐
```

**الكود / Code:**
```python
# apps/attendance/services.py
AttendanceService._trigger_late_block_notification(
    student=student,
    group=group,
    time_check=time_check,
    current_time=current_time
)
```

---

### 3. 🟡 منع مالي - طالب جديد / Financial Block (New)

**الزناد / Trigger:** الطالب يمسح QR، is_new_student = true، لا يوجد دفع

**القالب / Template:**
```
عزيزي ولي الأمر
الطالب/ة {student_name} لم يتمكن من الدخول
السبب: لم يتم تسجيل الدفع 💰
للطلاب الجدد: يجب الدفع قبل الحصة الأولى
الرجاء زيارة الإدارة لإتمام الإجراءات
```

**الكود / Code:**
```python
# apps/attendance/services.py
AttendanceService._trigger_financial_block_notification(
    student=student,
    group=group,
    financial_check=financial_check
)
```

---

### 4. 🟡 منع مالي - ديون / Financial Block (Debt)

**الزناد / Trigger:** طالب قديم، debt > 2 حصص

**القالب / Template:**
```
تنبيه مالي ⚠️
تم إيقاف الطالب/ة {student_name} مؤقتاً
عدد الحصص غير المدفوعة: {unpaid_sessions}
المبلغ المستحق: {due_amount} جنيه
الحد المسموح: حصتين فقط
الرجاء سداد المستحقات لاستئناف الحضور
```

---

### 5. 📢 تذكير بالدفع / Payment Reminder

**الزناد / Trigger:** مهمة Celery beat، يومياً الساعة 6 مساءً

**الشرط / Condition:** الطالب حضر 1 حصة غير مدفوعة (تحذير قبل الحظر)

**القالب / Template:**
```
تذكير 📢
عدد الحصص غير المدفوعة: {unpaid_sessions}
الحد المسموح: حصتين
المبلغ المستحق حتى الآن: {due_amount} جنيه
لتجنب الإيقاف، يرجى السداد قبل الحصة القادمة
```

---

### 6. 🙏 تأكيد استلام الدفع / Payment Confirmation

**الزناد / Trigger:** عند تسجيل الدفع في النظام

**القالب / Template:**
```
شكراً لكم 🙏
تم استلام دفعة بقيمة: {amount} جنيه
للطالب/ة: {student_name}
رقم الإيصال: {receipt_number}
التاريخ: {payment_date}
تم تحديث الرصيد ✅
```

**الكود / Code:**
```python
# apps/payments/services.py
CreditService._trigger_payment_confirmation(
    student=student,
    amount=amount,
    payment=payment
)
```

---

## التكوين والإعداد / Configuration

### 1. UltraMsg API Credentials

1. سجل في [UltraMsg.com](https://ultramsg.com/)
2. أنشئ instance جديد
3. احصل على:
   - `ULTRAMSG_INSTANCE_ID`
   - `ULTRAMSG_TOKEN`

### 2. متغيرات البيئة / Environment Variables

```bash
# .env file
# WhatsApp Settings (UltraMsg)
ULTRAMSG_INSTANCE_ID=instance12345
ULTRAMSG_TOKEN=token123456789

# Cost Tracking
WHATSAPP_COST_PER_MESSAGE=0.05
WHATSAPP_MONTHLY_BUDGET=500
WHATSAPP_CURRENCY=EGP

# Rate Limiting
MAX_MESSAGES_PER_HOUR=5

# Retry Configuration
MAX_NOTIFICATION_RETRIES=3
RETRY_DELAY_MINUTES=5

# Scheduled Tasks
DAILY_PAYMENT_REMINDER_TIME=18:00
```

### 3. إعدادات Celery Beat / Celery Beat Settings

```python
# config/celery.py
from celery.schedules import crontab

app.conf.beat_schedule = {
    # Daily payment reminders at 6 PM
    'daily-payment-reminders': {
        'task': 'apps.notifications.tasks.daily_payment_reminders_task',
        'schedule': crontab(hour=18, minute=0),
    },
    
    # Retry failed notifications every 10 minutes
    'retry-failed-notifications': {
        'task': 'apps.notifications.tasks.retry_failed_notifications_task',
        'schedule': crontab(minute='*/10'),
    },
    
    # Check notification costs daily at midnight
    'check-notification-costs': {
        'task': 'apps.notifications.tasks.check_notification_costs_task',
        'schedule': crontab(hour=0, minute=0),
    },
    
    # Cleanup old logs weekly
    'cleanup-old-logs': {
        'task': 'apps.notifications.tasks.cleanup_old_notification_logs_task',
        'schedule': crontab(day_of_week=0, hour=2, minute=0),
    },
}
```

---

## دليل النشر / Deployment Guide

### الخطوة 1: تشغيل الترحيلات / Run Migrations

```bash
python manage.py migrate
```

### الخطوة 2: إنشاء القوالب الافتراضية / Create Default Templates

```bash
python manage.py shell
>>> from apps.notifications.models import NotificationTemplate
>>> # Templates will be created automatically or use management command
```

### الخطوة 3: تشغيل Celery Worker و Beat / Start Celery Worker & Beat

```bash
# Terminal 1: Celery Worker
celery -A config worker -l INFO

# Terminal 2: Celery Beat
celery -A config beat -l INFO
```

### الخطوة 4: تشغيل Redis / Start Redis

```bash
redis-server
```

### الخطوة 5: اختبار الإرسال / Test Sending

```bash
# Visit: http://localhost:8000/notifications/test/
# Enter phone and message to test
```

---

## دليل الاختبار / Testing Guide

### اختبار السيناريوهات / Scenario Testing

#### 1. اختبار الحضور الناجح / Successful Attendance

```python
# test_scenarios.py
def test_attendance_success_notification():
    from apps.students.models import Student
    from apps.teachers.models import Group
    from apps.attendance.services import AttendanceService
    from django.utils import timezone
    
    student = Student.objects.get(student_code='1001')
    group = Group.objects.first()
    
    # Simulate scan
    result = AttendanceService.process_scan(
        student_code='1001',
        supervisor=None
    )
    
    assert result['status'] == 'present'
    assert result['allow_entry'] == True
    
    # Check Celery task was queued
    from apps.notifications.models import NotificationLog
    log = NotificationLog.objects.filter(
        student=student,
        notification_type='attendance_success'
    ).first()
    
    assert log is not None
```

#### 2. اختبار منع التأخير / Late Block

```python
def test_late_block_notification():
    # Mock current time to be late
    with patch('django.utils.timezone.now') as mock_now:
        mock_now.return_value = timezone.now() + timedelta(minutes=15)
        
        result = AttendanceService.process_scan('1001', None)
        
        assert result['status'] == 'late_blocked'
        assert result['allow_entry'] == False
        
        # Check notification was sent
        log = NotificationLog.objects.filter(
            notification_type='late_block'
        ).first()
        
        assert log is not None
        assert 'تأخير' in log.message
```

#### 3. اختبار الحظر المالي / Financial Block

```python
def test_financial_block_notification():
    # Set student to have debt
    enrollment = StudentGroupEnrollment.objects.get(
        student__student_code='1001'
    )
    enrollment.sessions_attended = 3
    enrollment.sessions_paid_for = 0
    enrollment.save()
    
    result = AttendanceService.process_scan('1001', None)
    
    assert result['status'] == 'blocked_payment'
    
    # Check notification
    log = NotificationLog.objects.filter(
        notification_type='financial_block_debt'
    ).first()
    
    assert log is not None
```

---

## استكشاف الأخطاء / Troubleshooting

### مشكلة: الإشعارات لا تصل / Notifications Not Delivered

**الحلول / Solutions:**

1. **تحقق من UltraMsg credentials:**
   ```bash
   echo $ULTRAMSG_INSTANCE_ID
   echo $ULTRAMSG_TOKEN
   ```

2. **تحقق من Celery worker:**
   ```bash
   celery -A config inspect active
   ```

3. **تحقق من Redis:**
   ```bash
   redis-cli ping
   # Should return PONG
   ```

4. **راجع السجلات:**
   ```bash
   tail -f logs/celery.log
   ```

### مشكلة: Rate Limit Exceeded

**الحل / Solution:**

تحقق من إعدادات الحد الأقصى:
```python
# apps/notifications/models.py
def check_rate_limit(self):
    return self.messages_last_hour < 5  # Max 5 per hour
```

### مشكلة: Templates Not Rendering

**الحل / Solution:**

تأكد من وجود المتغيرات المطلوبة:
```python
context = {
    'student_name': student.full_name,
    'group_name': group.group_name,
    'scan_time': scan_time.strftime('%H:%M'),
}
```

---

## مراقبة الأداء / Performance Monitoring

### مؤشرات الأداء الرئيسية / Key Metrics

- **معدل النجاح / Success Rate:** > 95%
- **زمن الاستجابة / Response Time:** < 500ms
- **التكلفة الشهرية / Monthly Cost:** < 500 EGP

### لوحة التحكم / Dashboard

زور: `/notifications/stats/`

---

## الصيانة / Maintenance

### مهام يومية / Daily Tasks

- مراجعة الإشعارات الفاشلة
- التحقق من التكاليف

### مهام أسبوعية / Weekly Tasks

- تنظيف السجلات القديمة
- مراجعة تفضيلات الإشعارات

### مهام شهرية / Monthly Tasks

- مراجعة تقارير التكلفة
- تحديث القوالب إذا لزم الأمر

---

## API Reference

### NotificationService

```python
from apps.notifications.services import NotificationService

service = NotificationService()

# Send attendance success
service.send_attendance_success(student, group, scan_time)

# Send late block
service.send_late_block(student, group, minutes_late, scheduled_time, scan_time)

# Send financial block (new)
service.send_financial_block_new_student(student, group)

# Send financial block (debt)
service.send_financial_block_debt(student, group, unpaid_sessions, due_amount)

# Send payment reminder
service.send_payment_reminder(student, group, unpaid_sessions, due_amount)

# Send payment confirmation
service.send_payment_confirmation(student, amount, receipt_number, payment_date)
```

---

## ملاحظات مهمة / Important Notes

1. **الإشعارات غير متزامنة / Async Notifications:**
   - جميع الإشعارات تُرسل عبر Celery tasks
   - لا تمنع عملية مسح QR

2. **إعادة المحاولة / Retry Logic:**
   - تلقائية: حتى 3 محاولات
   - تأخير أسي: 5، 10، 20 دقيقة

3. **الحد الأقصى / Rate Limiting:**
   - 5 رسائل في الساعة لكل ولي أمر
   - إشعارات الحظر إلزامية

4. **تتبع التكلفة / Cost Tracking:**
   - كل رسالة = 0.05 ج.م
   - تقارير شهرية متاحة

---

## الدعم / Support

للمساعدة والدعم:
- 📧 Email: support@example.com
- 📱 WhatsApp: +20xxxxxxxxx
- 🌐 Website: https://example.com

---

**آخر تحديث:** 2024-01-15
**الإصدار:** 2.0
