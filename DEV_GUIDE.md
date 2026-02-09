# دليل التطوير السريع - Development Quick Start

## تشغيل السيرفر مع Auto-Reload

### الطريقة الأولى: Using Development Script (مباشر على البورت 3000) ✅ موصى به
```bash
./dev_server.sh
```

### الطريقة الثانية: Manual Command
```bash
python manage.py runserver 0.0.0.0:3000
```

### الطريقة الثالثة: Using Docker Compose (Development Mode)
```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```
سيعمل على port 3000 مع Auto-reload

## المشاكل التي تم إصلاحها ✅

### 1. الصفحة الرئيسية (Dashboard)
- ✅ إصلاح أزرار "تسجيل الحضور" و "طالب جديد"
- ✅ تحسين CSS للأزرار لتعمل بشكل صحيح
- ✅ إضافة hover effects و cursor pointer

### 2. صفحة المواعيد (/teachers/bookings/)
- ✅ إصلاح عرض التقويم - كان يعطي server error
- ✅ إضافة template filter `dict_lookup` للوصول للبيانات بشكل صحيح
- ✅ تحسين CSS للأزرار في search page
- ✅ إصلاح زر "عرض التقويم"

### 3. صفحة الطلاب (/students/)
- ✅ تحسين تباعد زر "إضافة طالب" عن العنوان
- ✅ إضافة padding مناسب للـ header
- ✅ تحسين المظهر العام للصفحة

### 4. Auto-Reload Configuration
- ✅ إضافة `dev_server.sh` script للتطوير
- ✅ إضافة `docker-compose.dev.yml` لـ Docker development
- ✅ Documentation لكيفية التشغيل

## ملاحظات مهمة 📝

1. **Django Development Server** يعمل auto-reload تلقائياً عند أي تغيير في ملفات Python أو Templates
2. **CSS Changes**: قد تحتاج لعمل Hard Refresh (Ctrl+Shift+R) لرؤية تغييرات CSS
3. **Template Changes**: يتم تحديثها تلقائياً مع reload الصفحة

## ملفات تم تعديلها 📄

```
templates/
├── reports/dashboard.html           # إصلاح quick actions buttons
├── students/list.html                # تحسين header spacing
└── teachers/bookings/
    ├── calendar.html                 # إصلاح template syntax و server error
    └── search.html                   # تحسين buttons CSS

apps/teachers/templatetags/
└── dict_filters.py                   # NEW: template filter للوصول للـ dictionary values

docker-compose.dev.yml                # NEW: Development configuration
dev_server.sh                          # NEW: Quick start script
```

## اختبار التغييرات 🧪

1. شغل السيرفر باستخدام `./dev_server.sh`
2. افتح المتصفح على `http://localhost:3000`
3. اختبر:
   - ✅ الصفحة الرئيسية - اضغط على "تسجيل الحضور" و "طالب جديد"
   - ✅ صفحة المواعيد - اضغط على "عرض التقويم"
   - ✅ صفحة الطلاب - تأكد من تباعد زر "إضافة طالب"

## في حالة المشاكل 🔧

### الأزرار لا تعمل:
```bash
# Clear browser cache
Ctrl + Shift + R (Hard Refresh)
```

### Server Error في calendar:
```bash
# Restart the server
./dev_server.sh
```

### التغييرات لا تظهر:
```bash
# Collect static files
python manage.py collectstatic --clear --no-input
```

## Production Deployment

عند النشر للـ production، استخدم:
```bash
docker-compose up -d
```
(بدون docker-compose.dev.yml)
