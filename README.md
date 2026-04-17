# بداية — نظام إدارة تعليمي شامل

> **Bedaya (بداية)** — Education Management System  
> نظام إدارة متكامل للمراكز التعليمية والسناتر مبني بـ Django 5.0  
> الدومين: `sys.educore.software`

---

## فهرس المحتويات

- [نظرة عامة](#نظرة-عامة)
- [التقنيات المستخدمة](#التقنيات-المستخدمة)
- [بنية المشروع](#بنية-المشروع)
- [التطبيقات (Apps)](#التطبيقات-apps)
  - [accounts — المستخدمين والصلاحيات](#1-accounts--المستخدمين-والصلاحيات)
  - [students — إدارة الطلاب](#2-students--إدارة-الطلاب)
  - [teachers — المدرسين والقاعات والمجموعات](#3-teachers--المدرسين-والقاعات-والمجموعات)
  - [attendance — تسجيل الحضور](#4-attendance--تسجيل-الحضور)
  - [payments — المدفوعات والتسويات](#5-payments--المدفوعات-والتسويات)
  - [notifications — إشعارات الواتساب](#6-notifications--إشعارات-الواتساب)
  - [reports — التقارير ولوحة التحكم](#7-reports--التقارير-ولوحة-التحكم)
  - [core — النماذج الأساسية](#8-core--النماذج-الأساسية)
- [قاعدة البيانات (ERD)](#قاعدة-البيانات)
- [الـ APIs](#الـ-apis)
- [نظام الحضور — الخوارزمية](#نظام-الحضور--الخوارزمية)
- [نظام الاشتراكات](#نظام-الاشتراكات)
- [نظام الطباعة](#نظام-الطباعة)
- [الأمان والصلاحيات](#الأمان-والصلاحيات)
- [البنية التحتية والنشر](#البنية-التحتية-والنشر)
- [التشغيل المحلي](#التشغيل-المحلي)
- [التشغيل بـ Docker](#التشغيل-بـ-docker)
- [متغيرات البيئة](#متغيرات-البيئة)
- [الاختبارات](#الاختبارات)

---

## نظرة عامة

**بداية** هو نظام إدارة تعليمي مصمم خصيصاً للمراكز التعليمية (السناتر) في مصر. يدير:

| الوظيفة | الوصف |
|---------|-------|
| **الطلاب** | ملف شامل لكل طالب + كود فريد + باركود + كارنيه |
| **المدرسين** | بيانات المدرس + تخصصات متعددة + صورة شخصية |
| **المجموعات** | جداول ذكية مع كشف تعارض القاعات تلقائياً |
| **الحضور** | مسح الكود → كشف فوري للحالة + تسجيل تلقائي |
| **المدفوعات** | دفع شهري بالمجموعة + تسوية مستحقات المدرس |
| **الإشعارات** | واتساب تلقائي (حضور/غياب/تذكير دفع) |
| **التقارير** | داشبورد + تقارير حضور + تقارير مالية + سجل نشاط |

---

## التقنيات المستخدمة

| الطبقة | التقنية |
|--------|---------|
| **Backend** | Python 3.13 · Django 5.0.1 · Django REST Framework 3.14 |
| **Frontend** | Bootstrap 5 RTL · Cairo Font · Bootstrap Icons |
| **Database** | SQLite (dev) · PostgreSQL 15 (prod) |
| **Cache** | Redis 7 · django-redis |
| **Task Queue** | Celery 5.3 · django-celery-beat |
| **WhatsApp** | WASender API |
| **Barcode** | python-barcode (Code128) · qrcode · Pillow |
| **Reports** | ReportLab (PDF) · openpyxl (Excel) |
| **Static Files** | WhiteNoise 6.6 |
| **Server** | Gunicorn 21.2 (4 gthread workers) · Nginx |
| **Deploy** | Docker · docker-compose |
| **PWA** | Service Worker · Web App Manifest |

---

## بنية المشروع

```
SYSeducore/
├── config/                  # إعدادات Django
│   ├── settings.py          # الإعدادات الرئيسية
│   ├── urls.py              # الـ URL الرئيسي
│   ├── celery.py            # إعدادات Celery
│   ├── context_processors.py
│   ├── wsgi.py / asgi.py
│   └── settings_test.py     # إعدادات الاختبارات
│
├── apps/                    # التطبيقات
│   ├── accounts/            # المستخدمين والصلاحيات
│   ├── students/            # الطلاب
│   ├── teachers/            # المدرسين + القاعات + المجموعات + المواد
│   ├── attendance/          # الحضور والجلسات
│   ├── payments/            # المدفوعات والتسويات
│   ├── notifications/       # الواتساب والإشعارات
│   ├── reports/             # التقارير والداشبورد
│   └── core/                # SoftDeleteModel الأساسي
│
├── templates/               # قوالب HTML
│   ├── base.html            # القالب الرئيسي (sidebar + navbar)
│   ├── students/            # صفحات الطلاب + الكارنيه + الستيكر
│   ├── teachers/            # صفحات المدرسين والمجموعات
│   ├── attendance/          # الماسح والجلسات
│   ├── payments/            # المدفوعات والتسوية
│   ├── notifications/       # واتساب
│   ├── reports/             # التقارير
│   └── auth/                # تسجيل الدخول
│
├── static/                  # ملفات ثابتة
│   ├── css/                 # أنماط CSS
│   ├── js/                  # JavaScript
│   ├── icons/               # أيقونات PWA
│   ├── manifest.json        # PWA Manifest
│   └── sw.js                # Service Worker
│
├── media/                   # ملفات مرفوعة
│   ├── barcodes/            # صور الباركود المولدة
│   └── teachers/            # صور المدرسين
│
├── tests/                   # اختبارات إضافية
├── logs/                    # سجلات التطبيق
├── Dockerfile               # بناء Docker (multi-stage)
├── docker-compose.yml       # تشغيل كامل (DB + Redis + Web + Celery + Nginx)
├── nginx.conf               # إعدادات Nginx
├── requirements.txt         # التبعيات
└── manage.py
```

---

## التطبيقات (Apps)

### 1. accounts — المستخدمين والصلاحيات

**الموديلات:**

| Model | الوصف |
|-------|-------|
| `User` | مستخدم مخصص يرث من `AbstractUser` مع حقل `role` |

**الأدوار (Roles):**

| الدور | الكود | الصلاحيات |
|-------|-------|-----------|
| مدير النظام | `admin` | كل شيء — إدارة المستخدمين، التقارير المالية، الحذف |
| مشرف الحضور | `supervisor` | تسجيل الحضور، إدارة الطلاب والمجموعات |
| مدرس | `teacher` | عرض مجموعاته وطلابه فقط |

**Middleware:**
- `SystemLockoutMiddleware` — قفل النظام بالكامل (صفحة "النظام مغلق") عند `SYSTEM_LOCKOUT = True`
- `SessionTimeoutMiddleware` — تسجيل خروج تلقائي بعد ساعة من عدم النشاط

**Decorators:**
- `@admin_required` — للأدمن فقط
- `@supervisor_required` — للأدمن والمشرف
- `@teacher_required` — لأي مستخدم مسجل

**الروابط:**

| المسار | الوصف |
|--------|-------|
| `/accounts/login/` | تسجيل الدخول |
| `/accounts/logout/` | تسجيل الخروج |
| `/accounts/users/` | قائمة المستخدمين |
| `/accounts/users/create/` | إنشاء مستخدم |
| `/accounts/users/<id>/update/` | تعديل مستخدم |
| `/accounts/users/<id>/toggle/` | تفعيل/تعطيل مستخدم |

---

### 2. students — إدارة الطلاب

**الموديلات:**

| Model | الوصف |
|-------|-------|
| `Student` | الطالب — يرث `SoftDeleteModel` (حذف ناعم) |
| `StudentGroupEnrollment` | جدول وسيط لربط الطالب بالمجموعة + الحالة المالية |

**حقول الطالب الأساسية:**
- `student_code` — كود فريد يبدأ من 1001 (يتولد تلقائياً)
- `full_name` — الاسم الكامل
- `gender` — ذكر/أنثى
- `education_stage` — ابتدائي/إعدادي/ثانوي
- `education_year` — الصف الدراسي
- `education_type` — عام/لغات/تجريبي
- `student_phone` — رقم الطالب
- `parent_phone` — رقم ولي الأمر
- `groups` — M2M مع المجموعات (من خلال `StudentGroupEnrollment`)
- `subscription_expiry_date` — تاريخ انتهاء الاشتراك

**الحالة المالية (per enrollment):**

| الحالة | الكود | المعنى |
|--------|-------|--------|
| عادي | `normal` | يدفع السعر القياسي للمجموعة |
| مبلغ رمزي | `symbolic` | يدفع مبلغ مخصص (`custom_fee`) |
| إعفاء كامل | `exempt` | لا يدفع شيئاً |
| دفع بالحصة | `per_session` | يدفع حسب عدد الحصص |

**ميزات الطالب:**
- توليد **باركود Code128** (300 DPI، بدون نص)
- توليد **QR Code**
- **كارنيه طالب** (بطاقة هوية) بالباركود + بيانات المدرس
- **ستيكر حراري** (35mm × 10mm) للطباعة على طابعة لاصقات
- **اشتراك** 30 يوم مع تتبع الصلاحية

**الروابط:**

| المسار | الوصف |
|--------|-------|
| `/students/` | قائمة الطلاب |
| `/students/create/` | إضافة طالب |
| `/students/<id>/` | تفاصيل الطالب |
| `/students/<id>/update/` | تعديل |
| `/students/<id>/delete/` | حذف (ناعم) |
| `/students/<id>/id-card/` | كارنيه الطالب |
| `/students/<id>/id-card/print/` | كارنيه للطباعة (A4) |
| `/students/<id>/qr-ticket/` | ستيكر الباركود (35mm × 10mm) |
| `/students/<id>/toggle-status/` | تفعيل/تعطيل |

**API Endpoints:**

| المسار | الوصف |
|--------|-------|
| `/students/api/list/` | قائمة الطلاب (JSON) |
| `/students/api/statistics/` | إحصائيات |
| `/students/api/bulk-action/` | عمليات جماعية |
| `/students/api/<id>/barcode/` | صورة الباركود |
| `/students/api/<id>/groups/` | مجموعات الطالب |
| `/students/api/<id>/available-groups/` | المجموعات المتاحة للتسجيل |
| `/students/api/add-to-group/` | تسجيل في مجموعة |
| `/students/api/remove-from-group/` | إزالة من مجموعة |
| `/students/api/<id>/subscription/activate/` | تفعيل الاشتراك |
| `/students/api/<id>/subscription/status/` | حالة الاشتراك |

---

### 3. teachers — المدرسين والقاعات والمجموعات

**الموديلات:**

| Model | الوصف |
|-------|-------|
| `Teacher` | المدرس + التخصصات (M2M مع `Subject`) + صورة شخصية |
| `Subject` | المادة الدراسية (اسم + مرحلة) |
| `Room` | القاعة الدراسية (اسم + سعة قصوى) |
| `Group` | المجموعة — قلب النظام |
| `GroupSchedule` | جدول متعدد الأيام لكل مجموعة |

**المجموعة (Group) — التفاصيل:**
- `group_name` — اسم المجموعة
- `teacher` — FK → المدرس
- `room` — FK → القاعة (اختياري)
- `schedule_day` + `schedule_time` — يوم ووقت الحصة
- `duration_minutes` — مدة الحصة بالدقائق (افتراضي 120)
- `gender_type` — بنين/بنات/مختلط
- `education_stage` + `education_year` — المرحلة والصف
- `standard_fee` — السعر القياسي الشهري
- `center_percentage` — نسبة السنتر % (افتراضي 30%)
- `sessions_per_month` — عدد الحصص في الشهر (افتراضي 4)

**كشف تعارض القاعات (Smart Overlap Check):**
- عند حفظ مجموعة، يتحقق النظام من عدم وجود تداخل زمني في نفس القاعة
- المنطق: `start1 < end2 AND start2 < end1`
- يسمح بمجموعتين في نفس القاعة بشرط عدم تداخل الأوقات
- رسالة الخطأ تُظهر الوقت المتاح التالي

**الروابط:**

| المسار | الوصف |
|--------|-------|
| `/teachers/` | قائمة المدرسين |
| `/teachers/create/` | إضافة مدرس |
| `/teachers/<id>/` | تفاصيل المدرس |
| `/teachers/rooms/` | القاعات |
| `/teachers/groups/` | المجموعات |
| `/teachers/subjects/` | المواد الدراسية |
| `/teachers/bookings/` | بحث المواعيد |
| `/teachers/bookings/calendar/` | التقويم |

---

### 4. attendance — تسجيل الحضور

**الموديلات:**

| Model | الوصف |
|-------|-------|
| `Session` | الحصة — (مجموعة + تاريخ) — فريدة `unique_together` |
| `Attendance` | سجل حضور الطالب في حصة معينة |
| `ActivityLog` | سجل النشاط — من عمل إيه ومتى |

**حالات الحضور:**

| الحالة | الكود | المعنى |
|--------|-------|--------|
| حاضر | `present` | وصل في الوقت |
| متأخر | `late` | وصل بعد بداية الحصة ولكن قبل 10 دقائق |
| غائب | `absent` | لم يحضر أو تأخر أكثر من 10 دقائق |

**الخوارزمية (5 خطوات):**

```
1. جلب الطالب بـ student_code
2. التحقق من صلاحية الاشتراك (30 يوم)
3. مطابقة الجدول (اليوم + الوقت الحالي)
4. قاعدة 10 دقائق الصارمة:
   - الوصول المبكر: مسموح قبل 30 دقيقة من الحصة
   - الوصول بعد البداية: ≤ 10 دقائق → "متأخر" (مسموح)
   - الوصول بعد البداية: > 10 دقائق → "مرفوض" (BLOCK)
5. فحص مالي (الكشف الفوري):
   - هل دفع الشهر الحالي؟
   - هل عليه متأخرات؟
   - الحالة المالية (عادي/رمزي/معفي)
```

**الكشف الفوري (Instant Status):**
بمجرد مسح الكود، يظهر:
- حالة الدفع الشهري
- المتأخرات المالية
- الحالة المالية للطالب في المجموعة

**الروابط:**

| المسار | الوصف |
|--------|-------|
| `/attendance/scanner/` | صفحة الماسح (إدخال الكود يدوياً) |
| `/attendance/api/process-code/` | معالجة الكود (API) |
| `/attendance/api/today-stats/` | إحصائيات اليوم |
| `/attendance/api/today-sessions/` | حصص اليوم |
| `/attendance/session/<id>/` | تفاصيل الحصة |

**سجل النشاط (ActivityLog):**
يسجل كل عملية في النظام: من المستخدم + نوع العملية + التفاصيل + IP + التوقيت.

---

### 5. payments — المدفوعات والتسويات

**الموديلات:**

| Model | الوصف |
|-------|-------|
| `Payment` | سجل دفع — (طالب + مجموعة + شهر) — فريد `unique_together` |

**حالات الدفع:**

| الحالة | الكود |
|--------|-------|
| مدفوع | `paid` |
| مدفوع جزئياً | `partial` |
| غير مدفوع | `unpaid` |

**خدمة التسوية (SettlementService):**
- حساب إيرادات كل مجموعة في شهر معين
- حساب نسبة السنتر ونصيب المدرس
- تفصيل بالمجموعة (عدد الطلاب + الإيراد + النسب)

**الروابط:**

| المسار | الوصف |
|--------|-------|
| `/payments/` | قائمة المدفوعات |
| `/payments/<teacher_id>/settlement/` | تسوية مستحقات المدرس |

---

### 6. notifications — إشعارات الواتساب

**الموديلات:**

| Model | الوصف |
|-------|-------|
| `WhatsAppMessage` | رسالة واتساب (هاتف + نص + حالة + نوع + ارتباطات) |
| `WhatsAppTemplate` | قالب رسالة واتساب معرّف مسبقاً |

**أنواع الرسائل:**
- `student` — رسالة للطالب
- `parent` — رسالة لولي الأمر
- `group` — رسالة جماعية
- `attendance` — تقرير حضور
- `payment` — تقرير مدفوعات
- `custom` — رسالة مخصصة

**خدمة الواتساب (WhatsAppService):**
- إرسال فردي وجماعي عبر WASender API
- تنسيق أرقام الهواتف المصرية تلقائياً

**مهام Celery:**
- `send_attendance_notifications_task` — كل 5 دقائق: يرسل إشعارات الحضور/الغياب بعد 10 دقائق من بداية كل حصة
- `send_monthly_reminders_task` — أول كل شهر الساعة 9 صباحاً: تذكير بالدفع

**الروابط:**

| المسار | الوصف |
|--------|-------|
| `/notifications/whatsapp/` | لوحة الواتساب |
| `/notifications/whatsapp/send/` | إرسال رسالة |
| `/notifications/whatsapp/bulk/` | إرسال جماعي |
| `/notifications/whatsapp/history/` | سجل الرسائل |
| `/notifications/whatsapp/contacts/` | جهات الاتصال |
| `/notifications/whatsapp/templates/` | إدارة القوالب |

---

### 7. reports — التقارير ولوحة التحكم

**لوحة التحكم (Dashboard):**
- إحصائيات شاملة (طلاب/مدرسين/مجموعات/حضور اليوم)
- رسوم بيانية
- جدول حصص اليوم
- آخر النشاطات

**التقارير المتاحة:**

| التقرير | الوصف |
|---------|-------|
| تقرير الحضور | حضور/غياب بالتاريخ والمجموعة |
| تقرير المدفوعات | حالة الدفع بالشهر |
| التقرير المالي | إيرادات ومستحقات |
| سجل النشاط | كل العمليات في النظام |

**سلة المهملات (Recycle Bin):**
- عرض العناصر المحذوفة (حذف ناعم)
- استعادة العناصر
- حذف نهائي
- تفريغ السلة

**حماية بكلمة مرور:**
التقارير المالية محمية بكلمة مرور إضافية (متغير `REPORTS_PASSWORD`). الأدمن يتخطى هذا الشرط.

**الروابط:**

| المسار | الوصف |
|--------|-------|
| `/reports/` | الداشبورد (الصفحة الرئيسية) |
| `/reports/attendance/` | تقرير الحضور |
| `/reports/payments/` | تقرير المدفوعات |
| `/reports/financial/` | التقرير المالي |
| `/reports/activity-log/` | سجل النشاط |
| `/reports/recycle-bin/` | سلة المهملات |

---

### 8. core — النماذج الأساسية

| Class | الوصف |
|-------|-------|
| `SoftDeleteModel` | موديل abstract يوفر حذف ناعم (`deleted_at` + `deleted_by`) |
| `SoftDeleteManager` | Manager يستبعد المحذوفين تلقائياً |
| `AllObjectsManager` | Manager يشمل كل السجلات (محذوفة وغير محذوفة) |

**الحذف الناعم:**
- `student.soft_delete(user=request.user)` — حذف ناعم
- `student.restore()` — استعادة
- `Student.objects.all()` — الطلاب النشطين فقط
- `Student.all_objects.all()` — كل الطلاب (بما فيهم المحذوفين)

---

## قاعدة البيانات

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│      users       │     │     teachers     │     │      rooms       │
│──────────────────│     │──────────────────│     │──────────────────│
│ user_id (PK)     │     │ teacher_id (PK)  │     │ room_id (PK)     │
│ username         │     │ full_name        │     │ name             │
│ role             │     │ phone            │     │ capacity         │
│ phone            │     │ email            │     └──────────────────┘
└──────────────────┘     │ photo            │              │
        │                │ hire_date        │              │
        │                └──────────────────┘              │
        │                        │                         │
        │                ┌───────┴─────────┐              │
        │                │    subjects     │              │
        │                │ (M2M through)   │              │
        │                └─────────────────┘              │
        │                        │                         │
        │                ┌───────┴─────────────────────────┘
        │                │      groups       │
        │                │───────────────────│
        │                │ group_id (PK)     │
        │                │ group_name        │
        │                │ teacher (FK)      │
        │                │ room (FK)         │
        │                │ schedule_day/time │
        │                │ duration_minutes  │
        │                │ standard_fee      │
        │                │ center_percentage │
        │                │ gender_type       │
        │                │ education_stage   │
        │                └───────────────────┘
        │                        │
        │    ┌───────────────────┼───────────────────┐
        │    │                   │                   │
        │    ▼                   ▼                   ▼
┌────────────────────┐  ┌───────────────┐  ┌─────────────────────────┐
│     students       │  │   sessions    │  │  student_group_enrollment│
│────────────────────│  │───────────────│  │─────────────────────────│
│ student_id (PK)    │  │ session_id    │  │ student (FK)            │
│ student_code (UQ)  │  │ group (FK)    │  │ group (FK)              │
│ full_name          │  │ session_date  │  │ financial_status        │
│ gender             │  │ teacher_att.  │  │ custom_fee              │
│ education_*        │  └───────────────┘  └─────────────────────────┘
│ parent_phone       │          │
│ subscription_*     │          │
└────────────────────┘          ▼
        │              ┌───────────────┐
        │              │  attendances  │
        ├─────────────▶│───────────────│
        │              │ student (FK)  │
        │              │ session (FK)  │
        │              │ status        │
        │              │ scan_time     │
        │              │ supervisor(FK)│
        │              └───────────────┘
        │
        ▼
┌───────────────┐    ┌──────────────────────┐
│   payments    │    │  whatsapp_messages   │
│───────────────│    │──────────────────────│
│ student (FK)  │    │ phone_number         │
│ group (FK)    │    │ message_text         │
│ month         │    │ message_type         │
│ amount_due    │    │ student (FK)         │
│ amount_paid   │    │ group (FK)           │
│ status        │    │ status               │
└───────────────┘    └──────────────────────┘

┌──────────────────┐
│  activity_logs   │
│──────────────────│
│ user (FK)        │
│ action           │
│ description      │
│ target_model     │
│ target_id        │
│ ip_address       │
└──────────────────┘
```

---

## الـ APIs

النظام يستخدم **Django REST Framework** مع:
- `SessionAuthentication` — مصادقة بالجلسة
- `IsAuthenticated` — يجب تسجيل الدخول
- `DjangoFilterBackend` — فلترة

**API Routes:**

| المسار | الوصف |
|--------|-------|
| `/api/attendance/` | تسجيل الحضور (scan) |
| `/api/payments/` | إدارة المدفوعات |
| `/api/groups/filter/` | فلترة المجموعات |

---

## نظام الحضور — الخوارزمية

```
              ┌─────────────────┐
              │  مسح كود الطالب │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ البحث عن الطالب │──── لا يوجد ──▶ ❌ "طالب غير موجود"
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ فحص الاشتراك   │──── منتهي ───▶ ⚠️ "الاشتراك منتهي"
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ مطابقة الجدول  │──── لا حصة ──▶ ❌ "لا توجد حصة الآن"
              │ (اليوم+الوقت)  │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ قاعدة 10 دقائق │
              │                 │
              │ قبل 30 دقيقة ✅ │
              │ ≤ 10 دقائق ⚠️  │──── > 10 دقائق ──▶ ❌ BLOCK
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │  الكشف الفوري  │
              │ (الحالة المالية)│──── ⚠️ عرض التحذيرات
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │ ✅ تسجيل الحضور │
              └─────────────────┘
```

---

## نظام الاشتراكات

- كل طالب له **تاريخ انتهاء اشتراك** (`subscription_expiry_date`)
- عند التفعيل: `expiry = today + 30 يوم`
- الحالات: `active` / `expiring_soon` (≤ 3 أيام) / `expires_today` / `expired` / `inactive`
- عند المسح: إذا الاشتراك منتهي → تحذير

---

## نظام الطباعة

| النوع | القالب | الحجم | الوصف |
|-------|--------|-------|-------|
| كارنيه الطالب | `id_card.html` | A4 Portrait | بطاقة هوية مع صورة المدرس + باركود |
| كارنيه طباعة | `id_card_print.html` | A4 Portrait | نسخة بدون قالب base (طباعة مباشرة) |
| ستيكر حراري | `qr_ticket.html` | 35mm × 10mm | باركود + اسم + كود — للطابعات الحرارية |

**ستيكر الباركود (35mm × 10mm):**
- `@page { size: 35mm 10mm; margin: 0; }`
- باركود Code128 (9mm × 9mm) + اسم الطالب (5pt) + الكود (7pt)
- تعليمات طباعة بالعربي للمستخدم (حجم ورق مخصص + بدون هوامش)

---

## الأمان والصلاحيات

| الميزة | التفاصيل |
|--------|----------|
| **RBAC** | 3 أدوار (admin / supervisor / teacher) |
| **Session Timeout** | خروج تلقائي بعد ساعة |
| **CSRF** | محمي بـ Django CSRF مع trusted origins |
| **Rate Limiting** | `django-ratelimit` + nginx rate limiting |
| **HTTPS** | SSL redirect + HSTS (production) |
| **Security Headers** | X-Frame-Options DENY, XSS Protection, Content-Type nosniff |
| **Password Validation** | 4 validators + minimum 8 characters |
| **System Lockout** | قفل كامل للنظام بتغيير متغير واحد |
| **Report Password** | كلمة مرور إضافية للتقارير المالية |
| **Soft Delete** | لا يوجد حذف نهائي — كل شيء يُستعاد |
| **Activity Logging** | كل عملية مسجلة (مَن + ماذا + متى + IP) |

---

## البنية التحتية والنشر

```
                    ┌─────────────┐
                    │   Client    │
                    │ (Browser)   │
                    └──────┬──────┘
                           │ HTTPS
                    ┌──────▼──────┐
                    │   Nginx     │
                    │ (port 80)   │
                    │ rate-limit  │
                    │ gzip, cache │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       /static/      /media/      /* (proxy)
              │            │            │
              ▼            ▼            ▼
         staticfiles/  media/    ┌─────────────┐
                                │  Gunicorn    │
                                │ (port 3000)  │
                                │ 4 gthread    │
                                │ workers      │
                                └──────┬───────┘
                                       │
                              ┌────────┼────────┐
                              │        │        │
                              ▼        ▼        ▼
                          ┌──────┐ ┌──────┐ ┌──────┐
                          │SQLite│ │Redis │ │Celery│
                          │ (DB) │ │Cache │ │Worker│
                          └──────┘ └──────┘ └──────┘
```

**Production Stack:**
- **Server:** Gunicorn (4 gthread workers, port 3000)
- **Reverse Proxy:** Nginx (SSL termination, static files, rate limiting)
- **Database:** SQLite (current) / PostgreSQL 15 (Docker)
- **Cache:** Redis 7
- **Task Queue:** Celery + celery-beat
- **Static Files:** WhiteNoise (compressed + cached)

---

## التشغيل المحلي

```bash
# 1. استنساخ المشروع
git clone https://github.com/Cat9199/Education-Management-System.git
cd Education-Management-System

# 2. إنشاء بيئة افتراضية
python -m venv venv
source venv/bin/activate

# 3. تثبيت التبعيات
pip install -r requirements.txt

# 4. إنشاء ملف .env
cp .env.example .env  # أو أنشئه يدوياً

# 5. تطبيق الـ migrations
python manage.py migrate

# 6. إنشاء مستخدم أدمن
python manage.py createsuperuser

# 7. تشغيل السيرفر
python manage.py runserver 0.0.0.0:3000

# أو استخدم السكربت الجاهز:
bash dev_server.sh
```

---

## التشغيل بـ Docker

```bash
# 1. إنشاء ملف .env
cp .env.example .env

# 2. بناء وتشغيل كل الخدمات
docker-compose up -d --build

# الخدمات التي تعمل:
# - db          (PostgreSQL 15, port 5432)
# - redis       (Redis 7, port 6379)
# - web         (Django + Gunicorn, port 8000)
# - celery_worker
# - celery_beat
# - nginx       (port 80/443)
```

---

## متغيرات البيئة

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `SECRET_KEY` | — | مفتاح Django السري (غيّره في الإنتاج!) |
| `DEBUG` | `False` | وضع التطوير |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | النطاقات المسموحة |
| `DB_ENGINE` | `sqlite3` | محرك قاعدة البيانات |
| `DB_NAME` | `db.sqlite3` | اسم القاعدة |
| `DB_USER` / `DB_PASSWORD` | — | بيانات PostgreSQL |
| `DB_HOST` / `DB_PORT` | — | سيرفر القاعدة |
| `REDIS_URL` | `redis://localhost:6379/0` | رابط Redis |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker |
| `WASENDER_API_TOKEN` | — | توكن WASender API |
| `WASENDER_API_URL` | `https://wasenderapi.com/api/send-message` | رابط API |
| `REPORTS_PASSWORD` | `0000` | كلمة مرور التقارير |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:8000,...` | الأصول الموثوقة |
| `SYSTEM_LOCKOUT` | `False` | قفل النظام |
| `NOTIFICATION_METHOD` | `whatsapp` | طريقة الإشعارات |

---

## الاختبارات

```bash
# تشغيل كل الاختبارات
python manage.py test --settings=config.settings_test

# تشغيل اختبارات تطبيق معين
python manage.py test apps.students --settings=config.settings_test
python manage.py test apps.attendance --settings=config.settings_test

# اختبارات شاملة
python manage.py test apps.tests_comprehensive --settings=config.settings_test
```

---

## الترخيص

مشروع خاص — جميع الحقوق محفوظة.
