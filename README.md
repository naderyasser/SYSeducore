# نظام الحضور والمدفوعات التعليمي

# Educational Attendance and Payment System

## نظرة عامة | Overview

نظام متكامل لإدارة الحضور والمدفوعات في المراكز التعليمية باستخدام Django و JavaScript (MVC Pattern).

A comprehensive system for managing attendance and payments in educational centers using Django and JavaScript (MVC Pattern).

## المميزات | Features

### 1. نظام الحضور | Attendance System

- فحص ثلاثي (Triple Check) للتحقق من الحضور:
  - فحص التوقيت | Time Check
  - فحص اليوم | Day Check
  - فحص الحالة المالية | Financial Status Check
- مسح الباركود | Barcode Scanning
- تسجيل حضور المعلمين | Teacher Attendance Recording
- إلغاء الحصص | Session Cancellation

### 2. نظام المدفوعات | Payment System

- ثلاث حالات مالية للطلاب:
  - عادي (300 ج.م/شهر) | Normal (300 EGP/month)
  - رمزي (100 ج.م/شهر) | Symbolic (100 EGP/month)
  - معفى (0 ج.م) | Exempt (0 EGP)
- تسجيل المدفوعات | Payment Recording
- حساب مستحقات المدرسين | Teacher Settlement Calculation
- تقارير المدفوعات | Payment Reports

### 3. نظام الإشعارات | Notification System

- إرسال رسائل SMS للآباء | SMS Notifications to Parents
- إشعارات الحضور والغياب | Attendance/Absence Notifications
- تذكيرات المدفوعات الشهرية | Monthly Payment Reminders
- معالجة أوتوماتيكية باستخدام Celery | Automated Processing with Celery

### 4. التقارير | Reports

- تقارير الحضور | Attendance Reports
- تقارير المدفوعات | Payment Reports
- تقارير مستحقات المدرسين | Teacher Settlement Reports
- تصدير PDF/Excel/CSV | Export to PDF/Excel/CSV

## التقنيات المستخدمة | Technologies Used

### Backend

- **Django 5.x**: Web Framework
- **Django REST Framework (DRF)**: API Development
- **Celery + Redis**: Background Task Processing
- **Twilio**: SMS Integration
- **PostgreSQL**: Production Database
- **SQLite**: Development Database

### Frontend

- **Vanilla JavaScript**: No Framework (MVC Pattern)
- **Bootstrap 5.3**: UI Framework
- **RTL Support**: Arabic Language Interface

### Utilities

- **python-barcode**: Barcode Generation
- **reportlab**: PDF Generation
- **openpyxl**: Excel Export

## هيكل المشروع | Project Structure

```
EDU_SYS/
├── config/                    # Django Configuration
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   ├── asgi.py
│   └── celery.py
│
├── apps/                      # Django Apps
│   ├── accounts/             # User Management
│   │   ├── models.py        # Custom User Model
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── middleware.py    # SessionTimeoutMiddleware
│   │   └── decorators.py    # Permission Decorators
│   │
│   ├── teachers/            # Teacher & Group Management
│   │   ├── models.py        # Teacher, Group Models
│   │   ├── views.py
│   │   └── urls.py
│   │
│   ├── students/            # Student Management
│   │   ├── models.py        # Student Model
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── forms.py
│   │
│   ├── attendance/          # Attendance Management
│   │   ├── models.py        # Session, Attendance Models
│   │   ├── services.py      # AttendanceService (Triple Check)
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── api_views.py    # API Endpoints
│   │   └── api_urls.py
│   │
│   ├── payments/            # Payment Management
│   │   ├── models.py        # Payment Model
│   │   ├── services.py      # SettlementService
│   │   ├── views.py
│   │   └── urls.py
│   │
│   ├── notifications/       # Notification System
│   │   ├── services.py      # SMSService (Twilio)
│   │   ├── tasks.py         # Celery Tasks
│   │   └── urls.py
│   │
│   └── reports/             # Reports
│       ├── views.py
│       └── urls.py
│
├── static/                   # Static Files
│   ├── css/
│   │   └── base.css
│   ├── js/
│   │   ├── models/         # MVC Models
│   │   │   ├── Student.js
│   │   │   ├── Attendance.js
│   │   │   └── Payment.js
│   │   ├── views/          # MVC Views
│   │   │   ├── ScannerView.js
│   │   │   ├── DashboardView.js
│   │   │   └── ReportView.js
│   │   ├── controllers/    # MVC Controllers
│   │   │   ├── ScannerController.js
│   │   │   ├── StudentController.js
│   │   │   └── ReportController.js
│   │   ├── utils/
│   │   │   └── api.js
│   │   └── main.js
│   └── sounds/
│       ├── success.mp3
│       └── error.mp3
│
├── templates/               # HTML Templates
│   ├── base.html
│   ├── dashboard.html
│   ├── attendance/
│   │   ├── scanner.html
│   │   └── session_detail.html
│   ├── students/
│   │   ├── list.html
│   │   ├── detail.html
│   │   └── form.html
│   ├── reports/
│   │   ├── attendance.html
│   │   └── payments.html
│   └── auth/
│       └── login.html
│
├── utils/                   # Utility Scripts
│   ├── barcode_generator.py
│   └── pdf_generator.py
│
├── manage.py
├── requirements.txt
├── .env.example
└── README.md
```

## التثبيت | Installation

### المتطلبات | Requirements

- Python 3.11+
- PostgreSQL (for production)
- Redis (for Celery)

### خطوات التثبيت | Installation Steps

1. **استنساخ المشروع | Clone the Project**

   ```bash
   git clone <repository-url>
   cd EDU_SYS
   ```

2. **إنشاء بيئة افتراضية | Create Virtual Environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **تثبيت المتطلبات | Install Requirements**

   ```bash
   pip install -r requirements.txt
   ```

4. **إعداد المتغيرات البيئية | Setup Environment Variables**

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **إنشاء قاعدة البيانات | Create Database**

   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

6. **إنشاء مستخدم مسؤول | Create Superuser**

   ```bash
   python manage.py createsuperuser
   ```

7. **تشغيل الخادم | Run Development Server**

   ```bash
   python manage.py runserver
   ```

8. **تشغيل Redis و Celery | Run Redis and Celery**

   ```bash
   # Terminal 1: Redis
   redis-server

   # Terminal 2: Celery Worker
   celery -A config worker -l info

   # Terminal 3: Celery Beat
   celery -A config beat -l info
   ```

## الاستخدام | Usage

### تسجيل الدخول | Login

- الوصول إلى `/login/` | Access `/login/`
- أدخل اسم المستخدم وكلمة المرور | Enter username and password

### لوحة التحكم | Dashboard

- عرض إحصائيات عامة | View general statistics
- النشاطات الحديثة | Recent activities
- الحصص القادمة | Upcoming sessions

### مسح الباركود | Barcode Scanning

- الوصول إلى `/attendance/scanner/` | Access `/attendance/scanner/`
- مسح باركود الطالب | Scan student barcode
- عرض نتائج الفحص الثلاثي | View triple check results

### إدارة الطلاب | Student Management

- عرض قائمة الطلاب | View student list
- إضافة طالب جديد | Add new student
- تعديل بيانات الطالب | Edit student details
- عرض سجل الحضور | View attendance history

### التقارير | Reports

- تقرير الحضور | Attendance Report
- تقرير المدفوعات | Payment Report
- تقرير مستحقات المدرسين | Teacher Settlement Report
- تصدير التقارير | Export Reports

## الأدوار والصلاحيات | Roles and Permissions

### Admin (مسؤول)

- صلاحيات كاملة | Full permissions
- إدارة المستخدمين | User management
- إدارة المجموعات | Group management

### Supervisor (مشرف)

- إدارة الطلاب | Student management
- إدارة الحضور | Attendance management
- عرض التقارير | View reports

### Teacher (معلم)

- تسجيل حضور الطلاب | Record student attendance
- تسجيل حضوره | Record own attendance
- عرض تقارير مجموعته | View group reports

## API Endpoints

### Authentication

- `POST /api/auth/login/` - Login
- `POST /api/auth/logout/` - Logout

### Attendance

- `POST /api/attendance/scan/` - Process barcode scan
- `GET /api/attendance/session/{id}/` - Get session details
- `GET /api/attendance/session/{id}/attendance/` - Get session attendance

### Students

- `GET /api/students/` - List students
- `POST /api/students/` - Create student
- `GET /api/students/{id}/` - Get student details
- `PUT /api/students/{id}/` - Update student
- `DELETE /api/students/{id}/` - Delete student
- `GET /api/students/{id}/attendance/` - Get student attendance history

### Payments

- `GET /api/payments/` - List payments
- `POST /api/payments/record/` - Record payment
- `GET /api/payments/settlement/` - Get teacher settlement

### Reports

- `GET /api/reports/attendance/` - Attendance report
- `GET /api/reports/payment/` - Payment report
- `GET /api/reports/settlement/` - Settlement report
- `GET /api/reports/export/{format}/` - Export report (PDF/Excel/CSV)

## الأمان | Security

- حماية CSRF | CSRF Protection
- حماية XSS | XSS Protection
- حماية SQL Injection | SQL Injection Protection
- تشفير كلمات المرور | Password Encryption
- مهلة الجلسة | Session Timeout (1 hour)
- Rate Limiting | Rate Limiting

## النشر | Deployment

### Production Checklist

- [ ] Use PostgreSQL database
- [ ] Configure DEBUG=False
- [ ] Set up SSL/HTTPS
- [ ] Configure ALLOWED_HOSTS
- [ ] Set up static files serving
- [ ] Configure Celery with Redis
- [ ] Set up logging
- [ ] Configure email backend
- [ ] Set up monitoring
- [ ] Configure backup strategy

### Deployment with Gunicorn

```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

## الاختبار | Testing

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test apps.students

# Run with coverage
pip install coverage
coverage run --source='.' manage.py test
coverage report
```

## الدعم | Support

للدعم والاستفسارات | For support and inquiries:

- البريد الإلكتروني | Email: support@example.com
- الوثائق | Documentation: [Wiki Link]

## الترخيص | License

This project is licensed under the MIT License.

## المساهمون | Contributors

- [Your Name] - Initial development

## شكر وتقدير | Acknowledgments

- Django Team
- Bootstrap Team
- Twilio Team
- All open-source contributors
"# SYSeducore" 
