# 🔄 GitHub Actions Workflows - EDU_SYS

## 📋 Overview

هذا الدليل يشرح جميع الـworkflows المتوفرة في المشروع وكيفية استخدامها.

This guide explains all available workflows in the project and how to use them.

---

## 🚀 Available Workflows

### 1. **CI - Continuous Integration** ([ci.yml](./ci.yml))

**الغرض**: اختبار الكود تلقائياً عند كل commit/PR

**Purpose**: Automatically test code on every commit/PR

**متى يعمل**:
- عند Push على `master` أو `develop`
- عند فتح Pull Request

**When it runs**:
- On push to `master` or `develop` branches
- On pull request creation

**ماذا يفعل**:
1. ✅ **Code Quality Checks**: Black, isort, Flake8
2. 🔒 **Security Scan**: Bandit, Safety
3. 🧪 **Unit Tests**: pytest with coverage
4. ⚙️ **Django Checks**: System checks and migrations
5. 📦 **Build Test**: Collect static files

**المتطلبات**:
- لا يوجد - يعمل تلقائياً

**Requirements**:
- None - runs automatically

---

### 2. **Deploy to Production** ([deploy.yml](./deploy.yml))

**الغرض**: نشر التطبيق على بيئة الإنتاج

**Purpose**: Deploy application to production

**متى يعمل**:
- عند Push على `master`
- عند إنشاء tag بصيغة `v*.*.*`
- يدوياً من خلال Actions tab

**When it runs**:
- On push to `master` branch
- On tag creation (v*.*.*)
- Manual trigger via workflow_dispatch

**ماذا يفعل**:
1. 🔍 **Pre-deploy Checks**: Security and validation
2. 🧪 **Build & Test**: Full test suite
3. 🚀 **Deploy to Staging**: Auto-deploy to staging
4. 🎯 **Deploy to Production**: Manual approval required
5. 📊 **Post-deploy**: Create GitHub release

**المتطلبات**:
- تكوين Secrets في GitHub:
  - `STAGING_HOST`, `STAGING_USER`, `STAGING_SSH_KEY`
  - `PRODUCTION_HOST`, `PRODUCTION_USER`, `PRODUCTION_SSH_KEY`

**Requirements**:
- Configure GitHub Secrets:
  - Staging credentials
  - Production credentials

---

### 3. **Dependency Review** ([dependency-review.yml](./dependency-review.yml))

**الغرض**: فحص الثغرات الأمنية في المكتبات

**Purpose**: Scan dependencies for security vulnerabilities

**متى يعمل**:
- كل يوم اثنين الساعة 9 صباحاً (القاهرة)
- عند Pull Request
- يدوياً

**When it runs**:
- Every Monday at 9 AM Cairo time
- On pull requests
- Manual trigger

**ماذا يفعل**:
1. 🔍 **Vulnerability Scan**: Safety + pip-audit
2. 📦 **Outdated Packages**: Check for updates
3. 📄 **License Check**: Compliance verification
4. 🚨 **Create Issue**: Auto-create issue for critical vulnerabilities

**التقارير**:
- يتم رفع التقارير كـartifacts
- يتم إنشاء issue تلقائياً للثغرات الحرجة

**Reports**:
- Reports uploaded as artifacts
- Auto-creates issue for critical vulnerabilities

---

### 4. **CodeQL Security Analysis** ([codeql.yml](./codeql.yml))

**الغرض**: تحليل أمني متقدم للكود

**Purpose**: Advanced code security analysis

**متى يعمل**:
- عند Push/PR على `master` أو `develop`
- كل يوم أربعاء الساعة 10 صباحاً
- يدوياً

**When it runs**:
- On push/PR to `master`/`develop`
- Every Wednesday at 10 AM
- Manual trigger

**ماذا يفعل**:
1. 🔒 **Python Analysis**: Security vulnerabilities
2. 🌐 **JavaScript Analysis**: Frontend security
3. 📊 **Quality Checks**: Code quality issues

**النتائج**:
- تظهر في GitHub Security tab
- يتم إنشاء alerts تلقائياً

**Results**:
- Shown in GitHub Security tab
- Auto-creates security alerts

---

### 5. **Docker Build & Push** ([docker-build.yml](./docker-build.yml))

**الغرض**: بناء Docker images ونشرها

**Purpose**: Build and push Docker images

**متى يعمل**:
- عند Push على `master` أو `develop`
- عند إنشاء tag
- يدوياً

**When it runs**:
- On push to `master`/`develop`
- On tag creation
- Manual trigger

**ماذا يفعل**:
1. 🐳 **Build Image**: Multi-stage Docker build
2. 📤 **Push to Registry**: GitHub Container Registry
3. 🔍 **Security Scan**: Trivy vulnerability scan

**الـImages المتاحة**:
- `ghcr.io/YOUR_USERNAME/educore:master`
- `ghcr.io/YOUR_USERNAME/educore:develop`
- `ghcr.io/YOUR_USERNAME/educore:v1.0.0` (tags)

**Available Images**:
- Latest master branch
- Develop branch
- Semantic version tags

---

## 🎯 Workflow Best Practices

### للمطورين (For Developers)

1. **قبل Push**:
   ```bash
   # Run tests locally
   python manage.py test

   # Check code quality
   black --check .
   isort --check .
   flake8 .
   ```

2. **عند فتح PR**:
   - انتظر نجاح جميع الـCI checks
   - راجع تقارير Coverage
   - تأكد من عدم وجود ثغرات أمنية

3. **قبل Merge**:
   - تأكد من موافقة Code Review
   - تأكد من نجاح جميع الـtests
   - تحديث Documentation إذا لزم

### للـDeployment (For Deployment)

1. **Staging Deployment**:
   - يحدث تلقائياً عند Push على `master`
   - تحقق من Staging قبل Production

2. **Production Deployment**:
   - استخدم semantic versioning tags: `v1.0.0`
   - يتطلب موافقة يدوية (Manual approval)
   - تأكد من وجود backup

3. **Rollback**:
   - استخدم tag سابق
   - أو deploy من commit سابق

---

## 🔧 Configuration

### GitHub Secrets المطلوبة

```
# Deployment
STAGING_HOST=your-staging-server.com
STAGING_USER=deploy
STAGING_SSH_KEY=<private-key>

PRODUCTION_HOST=your-production-server.com
PRODUCTION_USER=deploy
PRODUCTION_SSH_KEY=<private-key>

# Database
DB_PASSWORD=<secure-password>

# Redis
REDIS_PASSWORD=<secure-password>

# WhatsApp
ULTRAMSG_INSTANCE_ID=<instance-id>
ULTRAMSG_TOKEN=<token>

# Security
SECRET_KEY=<django-secret-key>
```

### إضافة Secrets

1. اذهب إلى: `Settings` → `Secrets and variables` → `Actions`
2. اضغط `New repository secret`
3. أضف الـSecret name والـvalue
4. احفظ

---

## 📊 Monitoring Workflows

### عرض نتائج الـWorkflows

1. اذهب إلى tab `Actions` في GitHub
2. اختر الـworkflow المطلوب
3. راجع الـlogs والـartifacts

### تنزيل التقارير

1. افتح workflow run
2. انتقل لـ`Artifacts` في الأسفل
3. حمّل التقارير المطلوبة:
   - Coverage reports
   - Security reports
   - Test results

---

## 🚨 Troubleshooting

### CI Failures

**المشكلة**: Tests failing
**الحل**:
```bash
# Run locally first
python manage.py test --verbosity=2

# Check specific test
python manage.py test apps.attendance.tests
```

**المشكلة**: Code quality checks failing
**الحل**:
```bash
# Auto-fix formatting
black .
isort .

# Check what's wrong
flake8 . --show-source
```

### Deployment Failures

**المشكلة**: Migration errors
**الحل**:
1. تحقق من الـmigrations محلياً
2. تأكد من عدم وجود conflicts
3. راجع database backup

**المشكلة**: Static files not found
**الحل**:
```bash
# Collect static files
python manage.py collectstatic --no-input

# Check STATIC_ROOT settings
```

---

## 📚 Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Django Deployment Checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)

---

## 🤝 Contributing

عند إضافة workflow جديد:
1. أضف وصف مفصل في هذا الملف
2. أضف مثال للاستخدام
3. وثّق الـSecrets المطلوبة
4. اختبر الـworkflow قبل الـmerge

When adding new workflows:
1. Add detailed description here
2. Provide usage examples
3. Document required secrets
4. Test before merging

---

**تم الإنشاء بواسطة**: EDU_SYS DevOps Team
**آخر تحديث**: 2026-01-24
