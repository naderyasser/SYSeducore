# AGENTS.md - Educore System Guide for AI Coding Agents

## Project Overview

**Educore** (also known as SYSeducore) is a comprehensive Educational Attendance and Payment Management System designed for educational centers in Egypt. The system manages student attendance through barcode scanning, payment tracking, teacher settlements, and automated notifications.

### Key Features

1. **Attendance System** - Triple-check verification (Time, Day, Financial Status)
2. **Payment Management** - Three financial statuses (Normal: 300 EGP/month, Symbolic: custom fee, Exempt: free)
3. **Teacher & Group Management** - Room scheduling with conflict prevention
4. **Notification System** - WhatsApp integration via UltraMsg for parents
5. **Reports & Analytics** - PDF/Excel export capabilities

### Language & Localization

- **Primary Interface Language**: Arabic (RTL support)
- **Code Documentation**: Mixed Arabic and English
- **Timezone**: Africa/Cairo (Egypt)

---

## Technology Stack

### Backend

| Technology | Version | Purpose |
|------------|---------|---------|
| Django | 5.0.1 | Web Framework |
| Django REST Framework | 3.14.0 | API Development |
| Celery | 5.3.6 | Background Task Processing |
| django-celery-beat | 2.5.0 | Scheduled Tasks |
| PostgreSQL | 15 | Production Database |
| SQLite | - | Development Database |
| Redis | 7 | Cache & Message Broker |

### Frontend

| Technology | Purpose |
|------------|---------|
| Vanilla JavaScript | No framework (MVC Pattern) |
| Bootstrap 5.3 | UI Framework |
| HTML Templates | Django Template Language |

### External Services

- **UltraMsg**: WhatsApp messaging API
- **python-barcode**: Barcode generation
- **reportlab**: PDF generation
- **openpyxl**: Excel export

---

## Project Structure

```
SYSeducore/
├── apps/                           # Django Applications
│   ├── accounts/                   # User Management
│   │   ├── models.py               # Custom User model (Admin, Supervisor, Teacher roles)
│   │   ├── middleware.py           # SessionTimeoutMiddleware (1-hour timeout)
│   │   ├── decorators.py           # Permission decorators
│   │   └── views.py                # Authentication views
│   │
│   ├── students/                   # Student Management
│   │   ├── models.py               # Student, StudentGroupEnrollment
│   │   ├── forms.py                # Student forms
│   │   └── tests.py                # Model tests
│   │
│   ├── teachers/                   # Teacher & Group Management
│   │   ├── models.py               # Teacher, Room, Group
│   │   ├── forms.py                # Teacher/Group forms
│   │   └── tests.py                # Room conflict tests
│   │
│   ├── attendance/                 # Attendance Management
│   │   ├── models.py               # Session, Attendance
│   │   ├── services.py             # AttendanceService (core business logic)
│   │   ├── api_views.py            # API endpoints
│   │   └── tests.py                # Attendance logic tests
│   │
│   ├── payments/                   # Payment Management
│   │   ├── models.py               # Payment model
│   │   ├── services.py             # SettlementService
│   │   └── api_views.py            # Payment API
│   │
│   ├── notifications/              # Notification System
│   │   ├── services.py             # WhatsAppService (UltraMsg)
│   │   └── tasks.py                # Celery tasks
│   │
│   └── reports/                    # Reports & Analytics
│       └── views.py                # Dashboard, exports
│
├── config/                         # Django Configuration
│   ├── settings.py                 # Main settings (environment-based)
│   ├── urls.py                     # URL routing
│   ├── celery.py                   # Celery configuration
│   └── settings_test.py            # Test-specific settings
│
├── static/                         # Static Files
│   ├── js/                         # JavaScript (MVC Pattern)
│   │   ├── models/                 # Data models (Student.js, Attendance.js)
│   │   ├── views/                  # UI views (ScannerView.js)
│   │   ├── controllers/            # Business logic controllers
│   │   └── main.js                 # Application entry point
│   └── css/                        # Custom styles
│
├── templates/                      # HTML Templates
│   ├── base.html                   # Base template (RTL Arabic)
│   ├── attendance/                 # Scanner, session templates
│   ├── students/                   # Student list/detail templates
│   ├── teachers/                   # Teacher/group templates
│   └── reports/                    # Dashboard templates
│
├── tests/                          # Comprehensive Tests
│   └── test_comprehensive.py       # Integration tests (539 lines)
│
├── utils/                          # Utility Scripts
│   ├── barcode_generator.py        # Student barcode generation
│   └── pdf_generator.py            # PDF report generation
│
├── .github/workflows/              # CI/CD Pipelines
│   ├── ci.yml                      # Code quality, tests, security scans
│   ├── deploy.yml                  # Staging & production deployment
│   ├── docker-build.yml            # Docker image builds
│   ├── codeql.yml                  # Security analysis
│   └── dependency-review.yml       # Dependency checks
│
├── docker-compose.yml              # Full stack (DB, Redis, Web, Celery, Nginx)
├── Dockerfile                      # Multi-stage production build
├── nginx.conf                      # Reverse proxy configuration
├── requirements.txt                # Python dependencies
└── .env.example                    # Environment variables template
```

---

## Build and Test Commands

### Development Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup environment
cp .env.example .env
# Edit .env with your configuration

# 4. Database setup
python manage.py makemigrations
python manage.py migrate

# 5. Create superuser
python manage.py createsuperuser

# 6. Run development server
python manage.py runserver
```

### Running Tests

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test apps.students
python manage.py test apps.teachers
python manage.py test apps.attendance

# Run with verbosity
python manage.py test --verbosity=2

# Run comprehensive tests only
python manage.py test tests.test_comprehensive

# Run with coverage
coverage run --source='apps' manage.py test
coverage report -m
coverage html  # Generates htmlcov/index.html
```

### Code Quality

```bash
# Run Black formatter
black .

# Run isort (import sorting)
isort .

# Run Flake8 linter
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Security scan
bandit -r apps/ config/
```

### Celery (Background Tasks)

```bash
# Terminal 1: Redis server
redis-server

# Terminal 2: Celery Worker
celery -A config worker -l info

# Terminal 3: Celery Beat (scheduler)
celery -A config beat -l info
```

### Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f web
docker-compose logs -f celery_worker

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Stop services
docker-compose down

# Stop and remove volumes (⚠️ deletes data)
docker-compose down -v
```

---

## Code Style Guidelines

### Python (Django)

1. **Follow PEP 8** with 127 character line limit
2. **Docstrings**: Use descriptive docstrings in Arabic for business logic
3. **Type Hints**: Optional but encouraged
4. **Imports**: Grouped as Django, third-party, local
5. **Model Field Names**: Use English with Arabic `verbose_name`

```python
# Example model pattern
class Student(models.Model):
    """
    Student model for managing students.
    الطالب يمكنه الانتساب لأكثر من مجموعة
    """
    student_code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="كود الطالب",
        help_text="كود قصير ومميز (مثال: 1001)"
    )
    
    class Meta:
        db_table = 'students'
        verbose_name = 'طالب'
        verbose_name_plural = 'الطلاب'
```

### JavaScript (MVC Pattern)

The frontend follows MVC architecture:
- **Models**: Data structures and API communication
- **Views**: DOM manipulation and rendering
- **Controllers**: Event handling and business logic

```javascript
// Example pattern in static/js/
// models/Student.js - Data layer
// views/ScannerView.js - UI layer  
// controllers/ScannerController.js - Logic layer
```

### HTML Templates

- Use Django Template Language
- RTL support: `<html dir="rtl" lang="ar">`
- Bootstrap 5.3 classes
- Arabic labels with proper font support

---

## Testing Instructions

### Test Organization

Tests are distributed across the project:

1. **App-specific tests**: `apps/<app>/tests.py`
   - Model tests
   - View tests
   - Service logic tests

2. **Comprehensive tests**: `tests/test_comprehensive.py`
   - Integration tests
   - End-to-end workflows
   - Performance tests

### Writing Tests

```python
from django.test import TestCase
from apps.students.models import Student

class StudentModelTests(TestCase):
    """Tests for Student model"""
    
    def setUp(self):
        self.student = Student.objects.create(
            student_code='1001',
            full_name='Test Student',
            parent_phone='+20101234567'
        )
    
    def test_student_creation(self):
        """Test student is created correctly"""
        self.assertEqual(self.student.student_code, '1001')
        self.assertTrue(self.student.is_active)
```

### Key Test Scenarios

- **Attendance Logic**: Time checks (10-minute rule), financial validation
- **Room Conflicts**: Same room/day/time prevention
- **Payment Flow**: First month vs subsequent month rules
- **Authentication**: Role-based access control

---

## Security Considerations

### Implemented Security Measures

1. **Authentication & Authorization**
   - Custom User model with role-based access (Admin, Supervisor, Teacher)
   - Session timeout: 1 hour (`SESSION_COOKIE_AGE = 3600`)
   - CSRF protection enabled

2. **Data Protection**
   - Environment variables via `python-decouple`
   - Database credentials not in code
   - `.env` file in `.gitignore`

3. **Production Security** (settings.py)
   - `SECURE_SSL_REDIRECT` (when DEBUG=False)
   - `SESSION_COOKIE_SECURE = True`
   - `CSRF_COOKIE_SECURE = True`
   - `SECURE_HSTS_SECONDS = 31536000`
   - Rate limiting via `django-ratelimit`

4. **API Security**
   - Django REST Framework authentication
   - CORS configured for localhost only
   - XSS, CSRF, SQL Injection protection via Django

5. **Docker Security**
   - Non-root user (`educore` user, UID 1000)
   - Multi-stage build
   - Security headers in Nginx
   - Rate limiting zones

### Environment Variables (Required)

```bash
# Critical - Never commit these
SECRET_KEY=your-secret-key-here
DEBUG=False  # In production
ALLOWED_HOSTS=your-domain.com

# Database
DB_ENGINE=django.db.backends.postgresql
DB_NAME=educore
DB_USER=educore
DB_PASSWORD=secure-password
DB_HOST=db
DB_PORT=5432

# WhatsApp (UltraMsg)
ULTRAMSG_INSTANCE_ID=your-instance-id
ULTRAMSG_TOKEN=your-token
```

---

## Deployment Process

### CI/CD Pipeline (GitHub Actions)

The project uses GitHub Actions for automated CI/CD:

#### 1. CI Workflow (`.github/workflows/ci.yml`)

Triggers: Push/PR to `master` or `develop`

Jobs:
- **Code Quality**: Black, isort, Flake8
- **Security**: Bandit, Safety checks
- **Tests**: Django tests with PostgreSQL + Redis
- **Coverage**: Minimum 50% threshold
- **Build**: Static files collection, syntax check

#### 2. Deployment Workflow (`.github/workflows/deploy.yml`)

Triggers:
- Push to `master` → Auto-deploy to Staging
- Tag `v*.*.*` → Manual approval → Production

Features:
- Pre-deployment security checks
- Database backup before deploy
- Health checks after deploy
- GitHub Release creation

#### 3. Docker Build (`.github/workflows/docker-build.yml`)

- Multi-stage optimized builds
- Trivy vulnerability scanning
- Push to GitHub Container Registry
- Multi-platform support

### Manual Deployment

```bash
# Production deployment with Gunicorn
gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
```

### Production Checklist

- [ ] Use PostgreSQL database
- [ ] Set `DEBUG=False`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Set up SSL/HTTPS
- [ ] Configure static files serving (WhiteNoise/Nginx)
- [ ] Set up Celery with Redis
- [ ] Configure logging (`logs/` directory)
- [ ] Set up monitoring/health checks
- [ ] Configure backup strategy

---

## Core Business Logic

### Attendance Service (`apps/attendance/services.py`)

The 4-step attendance processing algorithm:

1. **Identification**: Look up student by `student_code`
2. **Schedule Matching**: Find group matching current day/time
3. **Time Check**: Strict 10-minute grace period
4. **Financial Check**: Verify payment status

```python
# Key constants
STRICT_GRACE_PERIOD_MINUTES = 10  # >10 min = BLOCK
EARLY_ARRIVAL_LIMIT_MINUTES = 30  # Can arrive 30 min early
```

### Financial Rules

- **First Month**: Must pay before attending (0 free sessions)
- **Subsequent Months**: 2 free sessions before payment required
- **Exempt Students**: Always allowed

### Room Scheduling

Unique constraint prevents conflicts:
```python
# Same room + same day + same time = BLOCKED
fields=['room', 'schedule_day', 'schedule_time']
```

---

## Key URLs

| URL | Purpose |
|-----|---------|
| `/admin/` | Django Admin Panel |
| `/accounts/login/` | Login page |
| `/attendance/scanner/` | Barcode scanner interface |
| `/students/` | Student list |
| `/teachers/` | Teacher list |
| `/reports/` | Dashboard & reports |
| `/api/attendance/scan/` | API: Process barcode scan |
| `/health/` | Health check endpoint |

---

## Troubleshooting

### Common Issues

1. **Migration Conflicts**
   ```bash
   python manage.py migrate <app> zero
   python manage.py makemigrations
   python manage.py migrate
   ```

2. **Celery Not Processing Tasks**
   - Check Redis is running: `redis-cli ping`
   - Verify Celery worker is started
   - Check `CELERY_BROKER_URL` in `.env`

3. **Static Files Not Loading**
   ```bash
   python manage.py collectstatic --no-input
   ```

4. **Tests Failing**
   ```bash
   # Keep test database for inspection
   python manage.py test --keepdb
   
   # Run specific test with verbosity
   python manage.py test apps.attendance.tests.AttendanceServiceTest.test_check_strict_time -v 3
   ```

---

## Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Main project documentation (Arabic/English) |
| `DEVELOPMENT_WORKFLOW.md` | Development workflow guide |
| `WORKFLOWS.md` | CI/CD workflows documentation |
| `EDUCORE_V2_SYSTEM_UPGRADE.md` | V2 upgrade guide |
| `ADMIN_PERMISSIONS_GUIDE.md` | Admin permissions reference |
| `CHANGELOG.md` | Version history |
| `ROADMAP.md` | Future development plans |

---

## Quick Reference

### Important Commands

```bash
# Development
python manage.py runserver              # Start dev server
python manage.py shell                  # Django shell
python manage.py dbshell               # Database shell

# Testing
python manage.py test                   # Run all tests
python manage.py test --parallel       # Parallel test execution

# Database
python manage.py makemigrations        # Create migrations
python manage.py migrate               # Apply migrations
python manage.py showmigrations        # List migrations
python manage.py sqlmigrate <app> <n>  # View SQL for migration

# Static/Media
python manage.py collectstatic         # Collect static files
python manage.py findstatic <file>     # Find static file

# Users
python manage.py createsuperuser       # Create admin user
python manage.py changepassword <user> # Change password

# Celery
celery -A config worker -l info        # Start worker
celery -A config beat -l info          # Start scheduler
celery -A config purge                 # Purge task queue
```

---

**Last Updated**: 2026-01-29  
**Project Version**: Educore V2  
**Django Version**: 5.0.1  
**Primary Language**: Arabic (RTL)
