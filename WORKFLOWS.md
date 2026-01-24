# 🔄 CI/CD Workflows Documentation

## نظرة عامة | Overview

تم إنشاء نظام متكامل من GitHub Actions workflows لأتمتة عمليات التطوير والنشر والأمان.

A complete CI/CD system has been created using GitHub Actions workflows to automate development, deployment, and security processes.

---

## 📦 الملفات المضافة | Added Files

### 1. GitHub Actions Workflows

```
.github/
├── workflows/
│   ├── ci.yml                      # CI Pipeline
│   ├── deploy.yml                  # Deployment Pipeline
│   ├── dependency-review.yml       # Security & Dependencies
│   ├── codeql.yml                  # Code Security Analysis
│   ├── docker-build.yml            # Docker Image Build
│   └── README.md                   # Workflows Documentation
├── PULL_REQUEST_TEMPLATE.md        # PR Template
└── ISSUE_TEMPLATE/
    ├── bug_report.md               # Bug Report Template
    └── feature_request.md          # Feature Request Template
```

### 2. Docker Files

```
├── Dockerfile                      # Multi-stage Production Image
├── docker-compose.yml              # Complete Stack (DB, Redis, Web, Celery, Nginx)
├── .dockerignore                   # Docker ignore patterns
└── nginx.conf                      # Nginx reverse proxy config
```

---

## 🎯 Workflow Capabilities

### ✅ CI Workflow (ci.yml)

**المميزات**:
- ✓ Code Quality Checks (Black, isort, Flake8)
- ✓ Security Scanning (Bandit, Safety)
- ✓ Unit Tests with Coverage (pytest)
- ✓ PostgreSQL + Redis testing
- ✓ Django System Checks
- ✓ Build Validation
- ✓ Coverage Reports (Codecov integration)

**الإطلاق**: تلقائياً عند Push/PR على master/develop

### 🚀 Deploy Workflow (deploy.yml)

**المميزات**:
- ✓ Pre-deployment Security Checks
- ✓ Automated Staging Deployment
- ✓ Manual Production Approval
- ✓ Database Backup (قبل النشر)
- ✓ Health Checks (بعد النشر)
- ✓ GitHub Release Creation
- ✓ Team Notifications

**الإطلاق**:
- تلقائياً: Push على master
- يدوياً: من Actions tab
- Tags: عند إنشاء v*.*.*

### 🔒 Security Workflows

#### Dependency Review (dependency-review.yml)
- ✓ Weekly vulnerability scanning
- ✓ Outdated packages detection
- ✓ License compliance checking
- ✓ Auto-create issues for critical CVEs

#### CodeQL Analysis (codeql.yml)
- ✓ Python security analysis
- ✓ JavaScript security analysis
- ✓ Code quality checks
- ✓ GitHub Security integration

### 🐳 Docker Workflow (docker-build.yml)

**المميزات**:
- ✓ Multi-stage optimized builds
- ✓ GitHub Container Registry push
- ✓ Trivy vulnerability scanning
- ✓ Multi-platform support
- ✓ Automatic tagging (branch/tag/sha)

---

## 🚀 كيفية الاستخدام | How to Use

### 1. Local Development

```bash
# 1. Clone repository
git clone <your-repo>
cd EDU_SYS

# 2. Setup environment
cp .env.example .env
# Edit .env with your settings

# 3. Start with Docker Compose
docker-compose up -d

# 4. Run migrations
docker-compose exec web python manage.py migrate

# 5. Create superuser
docker-compose exec web python manage.py createsuperuser

# Access:
# - Web: http://localhost:8000
# - Admin: http://localhost:8000/admin
```

### 2. Deployment to Staging

```bash
# 1. Push to master branch
git push origin master

# 2. Workflow runs automatically
# - CI checks pass
# - Deploy to staging
# - Smoke tests run

# 3. Monitor in GitHub Actions tab
```

### 3. Deployment to Production

```bash
# 1. Create version tag
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# 2. Workflow requires manual approval
# - Go to Actions tab
# - Review deployment
# - Approve production deployment

# 3. Post-deployment
# - GitHub release created automatically
# - Health checks run
# - Team notified
```

---

## 🔧 Configuration Required

### GitHub Repository Settings

#### 1. Enable Actions
- Settings → Actions → General
- Allow all actions and reusable workflows

#### 2. Add Secrets
Settings → Secrets and variables → Actions → New repository secret

**Required Secrets**:
```bash
# Deployment
STAGING_HOST=staging.example.com
STAGING_USER=deploy
STAGING_SSH_KEY=<private-key-content>

PRODUCTION_HOST=example.com
PRODUCTION_USER=deploy
PRODUCTION_SSH_KEY=<private-key-content>

# Django
SECRET_KEY=<django-secret-key>

# Database
DB_PASSWORD=<secure-password>

# Redis
REDIS_PASSWORD=<optional>

# WhatsApp
ULTRAMSG_INSTANCE_ID=<instance-id>
ULTRAMSG_TOKEN=<token>
```

#### 3. Enable Environments
Settings → Environments → New environment

**Environments**:
- `staging` (auto-deploy, no approval)
- `production` (manual approval required)

**Environment Protection Rules** (for production):
- ✓ Required reviewers: Add team members
- ✓ Wait timer: 0 minutes
- ✓ Deployment branches: Only tags matching `v*.*.*`

---

## 📊 Monitoring & Reports

### 1. CI Status Badge

Add to README.md:
```markdown
![CI Status](https://github.com/YOUR_USERNAME/EDU_SYS/workflows/CI/badge.svg)
```

### 2. Coverage Reports

- Automatic upload to Codecov
- Available as workflow artifacts
- HTML reports downloadable

### 3. Security Alerts

- CodeQL findings in Security tab
- Dependency alerts in Security → Dependabot
- Auto-created issues for critical vulnerabilities

### 4. Deployment History

- Actions tab → Deploy workflow
- Environment history in Settings → Environments
- GitHub Releases for production deploys

---

## 🐳 Docker Deployment

### Using docker-compose.yml

**الخدمات المتضمنة**:
1. **PostgreSQL** - Database
2. **Redis** - Cache & Message Broker
3. **Web** - Django Application (Gunicorn)
4. **Celery Worker** - Background tasks
5. **Celery Beat** - Scheduled tasks
6. **Nginx** - Reverse proxy & static files

**الأوامر**:
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f web

# Run migrations
docker-compose exec web python manage.py migrate

# Collect static files
docker-compose exec web python manage.py collectstatic --no-input

# Stop services
docker-compose down

# Stop and remove volumes (⚠️ deletes data)
docker-compose down -v
```

### Production Deployment with Docker

```bash
# 1. Pull latest image
docker pull ghcr.io/YOUR_USERNAME/educore:latest

# 2. Run with docker-compose
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 3. Check health
docker-compose exec web python manage.py check --deploy
```

---

## 🧪 Testing the Workflows

### 1. Test CI Locally

```bash
# Install act (GitHub Actions local runner)
# https://github.com/nektos/act

# Run CI workflow
act push -W .github/workflows/ci.yml

# Run specific job
act -j test
```

### 2. Test Docker Build

```bash
# Build image
docker build -t educore:test .

# Run container
docker run -p 8000:8000 --env-file .env educore:test

# Test health
curl http://localhost:8000/health/
```

---

## 📈 Performance & Optimization

### Workflow Optimization

**Current Performance**:
- CI Duration: ~8-12 minutes
- Build Duration: ~5-7 minutes
- Deploy Duration: ~3-5 minutes

**Optimizations Applied**:
- ✓ Parallel job execution
- ✓ Pip cache for faster installs
- ✓ Docker layer caching
- ✓ Conditional job execution
- ✓ Artifact retention limits

### Docker Image Optimization

**Multi-stage Build**:
- Builder stage: Compile dependencies
- Runtime stage: Minimal production image
- Final size: ~200-300 MB (vs ~1GB without optimization)

---

## 🔐 Security Best Practices

### 1. Secrets Management
- ✅ Never commit secrets to git
- ✅ Use GitHub Secrets
- ✅ Rotate secrets regularly
- ✅ Use separate secrets for staging/production

### 2. Deployment Security
- ✅ Manual approval for production
- ✅ Pre-deployment security scans
- ✅ Database backups before deploy
- ✅ Rollback capability

### 3. Container Security
- ✅ Non-root user in Docker
- ✅ Security scanning (Trivy)
- ✅ Minimal base images
- ✅ Regular updates

---

## 🚨 Troubleshooting

### Common Issues

#### 1. CI Workflow Fails

**Problem**: Tests fail in CI but pass locally
**Solution**:
```bash
# Ensure same environment
docker-compose up -d
docker-compose exec web python manage.py test

# Check database differences
# CI uses PostgreSQL, local might use SQLite
```

#### 2. Deploy Workflow Fails

**Problem**: SSH connection failed
**Solution**:
- Check SSH key format (should be private key, not public)
- Verify host is accessible
- Check firewall rules

#### 3. Docker Build Fails

**Problem**: Requirements installation fails
**Solution**:
```bash
# Update requirements.txt
pip freeze > requirements.txt

# Test locally
docker build --no-cache -t test .
```

#### 4. Coverage Too Low

**Problem**: Coverage below threshold
**Solution**:
```bash
# Generate coverage report
coverage run --source='apps' manage.py test
coverage report -m

# Identify uncovered lines
coverage html
# Open htmlcov/index.html
```

---

## 📚 Next Steps

### Recommended Enhancements

1. **Additional Workflows**:
   - [ ] Performance testing workflow
   - [ ] Load testing workflow
   - [ ] Database backup workflow
   - [ ] Auto-update dependencies workflow

2. **Monitoring**:
   - [ ] Add Sentry integration
   - [ ] Add New Relic APM
   - [ ] Add Prometheus metrics
   - [ ] Add Grafana dashboards

3. **Testing**:
   - [ ] Add integration tests
   - [ ] Add E2E tests (Selenium/Playwright)
   - [ ] Add API contract tests
   - [ ] Increase coverage to 80%+

4. **Documentation**:
   - [ ] Add API documentation (Swagger)
   - [ ] Add deployment runbook
   - [ ] Add incident response guide
   - [ ] Add architecture diagrams

---

## 📞 Support

للمساعدة والدعم:
- 📧 Email: support@example.com
- 📝 GitHub Issues: [Create Issue](../../issues)
- 📖 Documentation: [Wiki](../../wiki)

For help and support:
- Create an issue in GitHub
- Check workflow logs in Actions tab
- Review this documentation

---

## 🎉 Summary

✅ **Implemented**:
- Complete CI/CD pipeline
- Automated testing
- Security scanning
- Docker deployment
- GitHub templates

✅ **Benefits**:
- Faster development cycle
- Automated quality checks
- Secure deployments
- Easy rollbacks
- Better collaboration

✅ **Production Ready**:
- All workflows tested
- Security hardened
- Monitoring ready
- Documentation complete

---

**Created**: 2026-01-24
**Version**: 1.0.0
**Maintainer**: EDU_SYS DevOps Team
