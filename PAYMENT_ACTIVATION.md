# تفعيل الاشتراك من صفحة المدفوعات

## التحديث
تم إضافة زر "تسديد + تفعيل" في صفحة المدفوعات `/payments/` لتسديد الدفعة وتفعيل اشتراك الطالب بضغطة واحدة.

## الملفات المعدلة

### 1. `templates/payments/list.html`

#### إضافة عمود الإجراءات:
```html
<thead>
    <tr>
        <th>الطالب</th>
        <th>المجموعة</th>
        <th>المبلغ المستحق</th>
        <th>المبلغ المدفوع</th>
        <th>الحالة</th>
        <th>تاريخ الدفع</th>
        <th>الإجراءات</th>  <!-- ✅ جديد -->
    </tr>
</thead>
```

#### زر التسديد والتفعيل:
```html
<td>
    {% if payment.status != 'paid' %}
    <button onclick="markAsPaidAndActivate({{ payment.payment_id }}, {{ payment.student.student_id }})" 
            class="btn btn-sm btn-success">
        <i class="bi bi-check-circle me-1"></i>تسديد + تفعيل
    </button>
    {% else %}
    <span class="text-success"><i class="bi bi-check-circle-fill"></i></span>
    {% endif %}
</td>
```

#### JavaScript:
```javascript
function markAsPaidAndActivate(paymentId, studentId) {
    if (!confirm('هل تريد تسديد الدفعة وتفعيل اشتراك الطالب لمدة 30 يوم؟')) return;
    
    // 1. Mark payment as paid
    fetch(`/payments/api/${paymentId}/mark-paid/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': '{{ csrf_token }}'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 2. Activate subscription
            return fetch(`/students/api/${studentId}/subscription/activate/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': '{{ csrf_token }}'
                },
                body: 'days=30'
            });
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('✅ تم التسديد وتفعيل الاشتراك بنجاح!');
            location.reload();
        }
    });
}
```

### 2. `apps/payments/api_views.py`

#### API جديد لتسديد الدفعة:
```python
@login_required
@require_http_methods(["POST"])
def mark_as_paid(request, payment_id):
    """تسديد الدفعة بالكامل"""
    try:
        payment = Payment.objects.get(pk=payment_id)
        
        payment.amount_paid = payment.amount_due
        payment.status = 'paid'
        payment.payment_date = timezone.now()
        payment.save()
        
        return JsonResponse({
            'success': True,
            'message': 'تم تسديد الدفعة بنجاح',
            'payment': {
                'payment_id': payment.payment_id,
                'amount_paid': float(payment.amount_paid),
                'status': payment.status
            }
        })
    except Payment.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'الدفعة غير موجودة'
        }, status=404)
```

### 3. `apps/payments/api_urls.py`

```python
urlpatterns = [
    path('<int:payment_id>/record/', api_views.record_payment, name='api_record_payment'),
    path('<int:payment_id>/mark-paid/', api_views.mark_as_paid, name='api_mark_paid'),  # ✅ جديد
]
```

## كيفية الاستخدام

### الخطوات:
1. اذهب إلى `/payments/`
2. ابحث عن دفعة غير مسددة (حالة: "غير مدفوع" أو "جزئي")
3. اضغط على زر "تسديد + تفعيل"
4. سيتم:
   - ✅ تسديد الدفعة بالكامل
   - ✅ تفعيل اشتراك الطالب لمدة 30 يوم
   - ✅ تحديث الصفحة تلقائياً

### النتيجة:
- حالة الدفعة تتحول إلى "مدفوع" 🟢
- يظهر علامة ✓ بدلاً من الزر
- اشتراك الطالب يصبح نشط لمدة 30 يوم
- الطالب يستطيع تسجيل الحضور

## API Endpoints

### تسديد الدفعة
```
POST /payments/api/{payment_id}/mark-paid/

Response:
{
    "success": true,
    "message": "تم تسديد الدفعة بنجاح",
    "payment": {
        "payment_id": 380,
        "amount_paid": 100.00,
        "status": "paid"
    }
}
```

### تفعيل الاشتراك (موجود مسبقاً)
```
POST /students/api/{student_id}/subscription/activate/
Body: days=30

Response:
{
    "success": true,
    "message": "تم تفعيل اشتراك [الاسم] لمدة 30 يوم",
    ...
}
```

## الاختبار

```python
# Test payment + subscription
payment = Payment.objects.filter(status='unpaid').first()
payment.amount_paid = payment.amount_due
payment.status = 'paid'
payment.save()

# Activate subscription
payment.student.activate_subscription(days=30)

# Verify
assert payment.status == 'paid'
assert payment.student.is_subscription_active() == True
```

## الملخص

✅ **تم الإضافة:**
- زر "تسديد + تفعيل" في صفحة المدفوعات
- API لتسديد الدفعة بالكامل
- عملية واحدة تقوم بـ:
  1. تسديد الدفعة
  2. تفعيل الاشتراك (30 يوم)
  3. تحديث الصفحة

**الاستخدام:** اذهب إلى `/payments/` واضغط "تسديد + تفعيل" ✅
