# نظام الاشتراكات (Subscription System)

## نظرة عامة
نظام اشتراكات مدته 30 يوماً يربط تسجيل الحضور بحالة الدفع. بعد انتهاء الاشتراك، يتوقف النظام تلقائياً عن قبول حضور الطالب.

## 1. تعديلات قاعدة البيانات

### حقول جديدة في جدول `students`:

```sql
last_payment_date DATE NULL          -- تاريخ آخر دفع/تفعيل
subscription_expiry_date DATE NULL   -- تاريخ انتهاء الصلاحية (30 يوم)
```

### Migration:
```bash
python manage.py makemigrations students
python manage.py migrate students
```

## 2. Model Methods (apps/students/models.py)

### `is_subscription_active()`
```python
def is_subscription_active(self):
    """التحقق من صلاحية الاشتراك"""
    if not self.subscription_expiry_date:
        return False
    return timezone.now().date() <= self.subscription_expiry_date
```

### `activate_subscription(days=30)`
```python
def activate_subscription(self, days=30):
    """تفعيل اشتراك الطالب لمدة محددة"""
    today = timezone.now().date()
    self.last_payment_date = today
    self.subscription_expiry_date = today + timedelta(days=days)
    self.is_active = True
    self.save()
    return self.subscription_expiry_date
```

### `get_subscription_status()`
```python
def get_subscription_status(self):
    """الحصول على حالة الاشتراك مع التفاصيل"""
    # Returns:
    # - status: 'inactive', 'expired', 'expires_today', 'expiring_soon', 'active'
    # - message: رسالة وصفية
    # - days_remaining: عدد الأيام المتبقية
```

## 3. منطق التحقق في الحضور

### في `apps/attendance/services.py`:

```python
# الخطوة 1.5: التحقق من صلاحية الاشتراك
if not student.is_subscription_active():
    subscription_status = student.get_subscription_status()
    return {
        'success': False,
        'message': f'عفواً، اشتراك الطالب منتهي. {subscription_status["message"]}',
        'sound': 'error',
        'error_type': 'subscription_expired',
        'student_name': student.full_name,
        'subscription_status': subscription_status
    }
```

### رسائل الخطأ:
- **لم يتم التفعيل:** "عفواً، اشتراك الطالب منتهي. لم يتم تفعيل الاشتراك"
- **منتهي:** "عفواً، اشتراك الطالب منتهي. منتهي منذ X يوم"
- **ينتهي اليوم:** "عفواً، اشتراك الطالب منتهي. ينتهي اليوم"

## 4. API Endpoints

### تفعيل الاشتراك
```
POST /students/api/{student_id}/subscription/activate/
Body: days=30 (optional, default 30)

Response:
{
    "success": true,
    "message": "تم تفعيل اشتراك [الاسم] لمدة 30 يوم",
    "student": {
        "student_id": 1,
        "full_name": "...",
        "last_payment_date": "2026-02-10",
        "subscription_expiry_date": "2026-03-12"
    },
    "subscription_status": {
        "status": "active",
        "message": "نشط - متبقي 30 يوم",
        "days_remaining": 30
    }
}
```

### الحصول على حالة الاشتراك
```
GET /students/api/{student_id}/subscription/status/

Response:
{
    "success": true,
    "student": {
        "student_id": 1,
        "full_name": "...",
        "last_payment_date": "2026-02-10",
        "subscription_expiry_date": "2026-03-12",
        "is_active": true
    },
    "subscription_status": {
        "status": "active",
        "message": "نشط - متبقي 30 يوم",
        "days_remaining": 30
    }
}
```

## 5. واجهة المستخدم

### صفحة تفاصيل الطالب (`templates/students/detail.html`)

#### زر التفعيل:
```html
<button onclick="activateSubscription({{ student.student_id }})" class="btn btn-success">
    <i class="bi bi-check-circle me-1"></i>تفعيل الاشتراك (30 يوم)
</button>
```

#### عرض الحالة:
```html
{% if student.subscription_expiry_date %}
    <div class="alert alert-{% if student.is_subscription_active %}success{% else %}danger{% endif %}">
        {% if student.is_subscription_active %}
            الاشتراك نشط حتى: {{ student.subscription_expiry_date }}
        {% else %}
            الاشتراك منتهي منذ: {{ student.subscription_expiry_date }}
        {% endif %}
    </div>
{% else %}
    <div class="alert alert-warning">
        لم يتم تفعيل الاشتراك
    </div>
{% endif %}
```

#### JavaScript:
```javascript
function activateSubscription(studentId) {
    const days = prompt('عدد الأيام (افتراضي 30):', '30');
    if (!days) return;

    fetch(`/students/api/${studentId}/subscription/activate/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': '{{ csrf_token }}'
        },
        body: `days=${days}`
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(data.message);
            location.reload();
        }
    });
}
```

## 6. حالات الاشتراك (Subscription States)

| Status | Description | Days Remaining | Color |
|--------|-------------|----------------|-------|
| `inactive` | لم يتم التفعيل | 0 | ⚪ Gray |
| `expired` | منتهي | < 0 | 🔴 Red |
| `expires_today` | ينتهي اليوم | 0 | 🟠 Orange |
| `expiring_soon` | ينتهي قريباً | 1-3 | 🟡 Yellow |
| `active` | نشط | > 3 | 🟢 Green |

## 7. سيناريوهات الاستخدام

### السيناريو 1: تفعيل اشتراك جديد
```python
student = Student.objects.get(student_code='1001')
student.activate_subscription(days=30)
# Result: last_payment_date = today, expiry = today + 30 days
```

### السيناريو 2: محاولة حضور مع اشتراك منتهي
```python
# في الماسح الضوئي
result = AttendanceService.process_scan(student_code='1001', supervisor=user)
# Result: {'success': False, 'error_type': 'subscription_expired', ...}
```

### السيناريو 3: تجديد اشتراك منتهي
```python
student.activate_subscription(days=30)
# يتم تحديث التواريخ وإعادة التفعيل
```

## 8. الأتمتة (Cron Job) - اختياري

### إنشاء Management Command:
```python
# apps/students/management/commands/expire_subscriptions.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.students.models import Student

class Command(BaseCommand):
    help = 'تعطيل الطلاب الذين انتهت اشتراكاتهم'

    def handle(self, *args, **options):
        today = timezone.now().date()
        expired = Student.objects.filter(
            subscription_expiry_date__lt=today,
            is_active=True
        )
        count = expired.update(is_active=False)
        self.stdout.write(f'تم تعطيل {count} طالب')
```

### إضافة Cron Job:
```bash
# crontab -e
0 0 * * * cd /path/to/project && python manage.py expire_subscriptions
```

## 9. الاختبار

### Test 1: تفعيل اشتراك
```python
student = Student.objects.first()
expiry = student.activate_subscription(days=30)
assert student.is_subscription_active() == True
```

### Test 2: التحقق من الحالة
```python
status = student.get_subscription_status()
assert status['status'] == 'active'
assert status['days_remaining'] == 30
```

### Test 3: منع الحضور
```python
student.subscription_expiry_date = timezone.now().date() - timedelta(days=1)
student.save()
result = AttendanceService.process_scan(student.student_code, supervisor)
assert result['success'] == False
assert result['error_type'] == 'subscription_expired'
```

## 10. الملفات المعدلة

1. ✅ `apps/students/models.py` - إضافة حقول وdوال
2. ✅ `apps/students/api_views.py` - API endpoints
3. ✅ `apps/students/urls.py` - URLs
4. ✅ `apps/attendance/services.py` - منطق التحقق
5. ✅ `templates/students/detail.html` - واجهة التفعيل
6. ✅ `apps/students/migrations/0004_*.py` - Migration

## 11. الخلاصة

✅ **تم التنفيذ بالكامل:**
- حقول الاشتراك في قاعدة البيانات
- دوال التفعيل والتحقق
- منطق منع الحضور للمنتهية صلاحيتهم
- API endpoints للتفعيل والاستعلام
- واجهة مستخدم في صفحة الطالب
- رسائل خطأ واضحة ومحددة

**الاستخدام:**
1. اذهب إلى صفحة تفاصيل الطالب
2. اضغط "تفعيل الاشتراك (30 يوم)"
3. سيتم تفعيل الاشتراك لمدة 30 يوم
4. عند انتهاء الصلاحية، لن يتمكن الطالب من تسجيل الحضور

**ملاحظة:** النظام صارم - لا يوجد "سماح مؤقت". دفع = دخول.
