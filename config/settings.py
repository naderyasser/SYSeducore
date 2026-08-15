"""
Django settings for attendance_system project.
"""

import os
import sys
from pathlib import Path

from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured

_SETTINGS_MODULE = os.environ.get('DJANGO_SETTINGS_MODULE', '')
TESTING = (
    'test' in sys.argv
    or os.path.basename(sys.argv[0] or '').startswith('pytest')
    or _SETTINGS_MODULE.endswith('settings_test')
    or any('settings_test' in arg for arg in sys.argv if arg.startswith('--settings'))
)

# Optional Celery import
try:
    from celery.schedules import crontab
except ImportError:
    crontab = None

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

# SECURITY WARNING: keep the secret key used in production secret!
# SEC-04: a development-only fallback is provided when DEBUG (or the test runner)
# is active. With DEBUG=False the application REFUSES to boot unless a real
# SECRET_KEY is supplied through the environment.
DEV_INSECURE_SECRET_KEY = 'django-insecure-change-this-in-production'

# Placeholder values that must never be accepted as a production secret.
_INSECURE_SECRET_KEYS = {
    '',
    DEV_INSECURE_SECRET_KEY,
    'your-secret-key-here-change-in-production',
    'change-me',
}

SECRET_KEY = config('SECRET_KEY', default='')

if SECRET_KEY in _INSECURE_SECRET_KEYS:
    if DEBUG or TESTING:
        SECRET_KEY = DEV_INSECURE_SECRET_KEY
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY is missing or still set to a well-known placeholder while "
            "DEBUG=False. Refusing to start. Generate a unique key, e.g.: "
            "python -c \"from django.core.management.utils import get_random_secret_key; "
            "print(get_random_secret_key())\" and set it in the SECRET_KEY environment "
            "variable (see .env.example)."
        )

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
if TESTING and 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'corsheaders',
    'django_filters',
    'django_celery_beat',
    
    # Local apps
    'apps.core',
    'apps.accounts',
    'apps.students',
    'apps.teachers',
    'apps.attendance',
    'apps.payments',
    'apps.notifications',
    'apps.reports',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.SystemLockoutMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.accounts.middleware.SessionTimeoutMiddleware',
]

# System Lockout - set SYSTEM_LOCKOUT=True in the environment to block all access.
# SEC-13: env-driven so the kill-switch can be flipped without a code change/redeploy.
SYSTEM_LOCKOUT = config('SYSTEM_LOCKOUT', default=False, cast=bool)

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.notification_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.sqlite3'),
        'NAME': config('DB_NAME', default=BASE_DIR / 'db.sqlite3'),
        'USER': config('DB_USER', default=''),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default=''),
        'PORT': config('DB_PORT', default=''),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8}
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Custom User Model
AUTH_USER_MODEL = 'accounts.User'


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'ar-eg'

TIME_ZONE = 'Africa/Cairo'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# WhiteNoise for production static files.
# SEC-10: STATICFILES_STORAGE is deprecated in Django 5.0 and removed in 5.1,
# so the storage backends are declared through the STORAGES dict instead.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Messages framework - map Django tags to Bootstrap classes
from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {
    message_constants.DEBUG: 'secondary',
    message_constants.INFO: 'info',
    message_constants.SUCCESS: 'success',
    message_constants.WARNING: 'warning',
    message_constants.ERROR: 'danger',
}


# Django REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
}


# CORS Settings
# SEC-12: env-driven, same pattern as CSRF_TRUSTED_ORIGINS.
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:8000,http://127.0.0.1:8000,https://sys.educore.software',
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True


# Session Settings
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_COOKIE_HTTPONLY = True
# SEC-14: writing the session row on *every* request (including static/media) is a
# needless DB write. SessionTimeoutMiddleware already touches the session on each
# authenticated request, which keeps the inactivity window accurate.
SESSION_SAVE_EVERY_REQUEST = False
SESSION_ENGINE = 'django.contrib.sessions.backends.db'


# CSRF Settings
CSRF_COOKIE_HTTPONLY = False
CSRF_USE_SESSIONS = False
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='http://localhost:8000,https://sys.educore.software', cast=Csv())
CSRF_FAILURE_VIEW = 'apps.accounts.views.csrf_failure'

# Proxy SSL Header.
# SEC-05: only trust X-Forwarded-Proto when the deployment really is behind a
# reverse proxy that *overwrites* the header. If gunicorn is reachable directly,
# a client could otherwise spoof `X-Forwarded-Proto: https` and defeat
# SECURE_SSL_REDIRECT / "secure" cookies. Default is OFF (fail closed).
TRUST_PROXY_SSL_HEADER = config('TRUST_PROXY_SSL_HEADER', default=False, cast=bool)
if TRUST_PROXY_SSL_HEADER:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Redis Configuration
REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

# SEC-09: a Redis outage must not turn every rate-limited view (login, scanner)
# into a 500. IGNORE_EXCEPTIONS makes cache operations degrade to a miss, and the
# short socket timeouts stop requests from hanging on an unreachable Redis.
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': True,
            'SOCKET_CONNECT_TIMEOUT': 3,  # seconds
            'SOCKET_TIMEOUT': 3,  # seconds
        },
    }
}

# Log the exceptions that IGNORE_EXCEPTIONS swallows, so an outage is visible.
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True


# Celery Configuration
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# Celery Beat Schedule (only if celery is installed)
if crontab is not None:
    CELERY_BEAT_SCHEDULE = {
        'send-attendance-notifications': {
            'task': 'apps.notifications.tasks.send_attendance_notifications_task',
            'schedule': crontab(minute='*/5'),  # Every 5 minutes
        },
        'send-monthly-reminders': {
            'task': 'apps.notifications.tasks.send_monthly_reminders_task',
            'schedule': crontab(hour=9, minute=0, day_of_month=1),  # 1st of every month at 9 AM
        },
        'auto-mark-absent-sessions': {
            'task': 'apps.attendance.tasks.auto_mark_absent_sessions',
            'schedule': crontab(minute='*/2'),  # Every 2 minutes
        },
        'check-billing-cycles': {
            'task': 'apps.attendance.tasks.check_billing_cycles',
            'schedule': crontab(hour='*/6'),  # Every 6 hours
        },
    }
else:
    CELERY_BEAT_SCHEDULE = {}


# WhatsApp Configuration (Wapilot API v2)
#
# The centre's WhatsApp account lives on Wapilot (https://app.wapilot.net), not
# on WASender — the provider this project originally shipped against. The two
# APIs differ in every part of the contract, so the transport in
# ``apps.notifications.services`` was rewritten rather than re-pointed:
#
#   endpoint  POST {WAPILOT_API_BASE_URL}/{WAPILOT_INSTANCE_ID}/send-message
#   auth      ``token: <api token>``   (not ``Authorization: Bearer``)
#   body      ``{"chat_id": ..., "text": ...}``   (not ``{"to": ..., "text": ...}``)
#
# ``WAPILOT_INSTANCE_ID`` is the instance *name* shown in the dashboard
# (e.g. ``instance5136``) — the bare digits are rejected with 404.
WAPILOT_API_TOKEN = config('WAPILOT_API_TOKEN', default='')
WAPILOT_INSTANCE_ID = config('WAPILOT_INSTANCE_ID', default='')
WAPILOT_API_BASE_URL = config('WAPILOT_API_BASE_URL', default='https://api.wapilot.net/api/v2')

# Notification Settings
NOTIFICATION_METHOD = config('NOTIFICATION_METHOD', default='whatsapp')

# If True, block attendance for first-month students who haven't paid.
# If False, give first-month students the same 2-session grace period as returning students.
ENABLE_FIRST_MONTH_STRICT_PAYMENT = config('ENABLE_FIRST_MONTH_STRICT_PAYMENT', default=True, cast=bool)


# GLM-4 API Configuration
GLM4_API_KEY = config('GLM4_API_KEY', default='')
GLM4_API_URL = config('GLM4_API_URL', default='https://api.glm4.example.com')


# The health endpoint (OPS-06) must stay reachable over plain HTTP so container
# and load-balancer probes are not answered with a 301 to https.
SECURE_REDIRECT_EXEMPT = [r'^health/?$']


# Security Settings (for production)
if not DEBUG and not TESTING:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# Rate Limiting
RATELIMIT_ENABLE = config('RATELIMIT_ENABLE', default=True, cast=bool)


# Logging
LOG_DIR = Path(config('LOG_DIR', default='logs'))
if not LOG_DIR.is_absolute():
    LOG_DIR = BASE_DIR / LOG_DIR

# SEC-11: never let a read-only (or otherwise unwritable) filesystem crash the
# settings import. If the log directory cannot be created/written we simply fall
# back to console-only logging instead of taking the whole process down.
LOG_TO_FILE = True
try:
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.access(LOG_DIR, os.W_OK):
        LOG_TO_FILE = False
except OSError:
    LOG_TO_FILE = False

_LOG_HANDLERS = {
    'console': {
        'level': 'INFO',
        'class': 'logging.StreamHandler',
    },
}

if LOG_TO_FILE:
    # SEC-08: rotate the log file instead of growing without bound.
    _LOG_HANDLERS['file'] = {
        'level': 'INFO',
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / 'django.log'),
        'maxBytes': 10 * 1024 * 1024,  # 10 MB
        'backupCount': 5,
        'encoding': 'utf-8',  # Arabic log messages
    }

_ACTIVE_LOG_HANDLERS = list(_LOG_HANDLERS.keys())

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': _LOG_HANDLERS,
    'root': {
        'handlers': _ACTIVE_LOG_HANDLERS,
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': _ACTIVE_LOG_HANDLERS,
            'level': 'INFO',
            'propagate': False,
        },
    },
}
