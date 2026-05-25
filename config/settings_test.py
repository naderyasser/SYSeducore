"""
Test settings for SYSeducore project.
Uses SQLite for faster testing without PostgreSQL.
"""
from .settings import *

# Use SQLite for tests
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Disable password hashers for faster tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable debug
DEBUG = False

# Use simple cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Disable Celery
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable SSL redirect for tests
SECURE_SSL_REDIRECT = False

# Disable rate limiting for tests (except explicit rate-limit tests)
RATELIMIT_ENABLE = False

# Disable WhatsApp/messaging for tests (WhatsApp views redirect when disabled)
NOTIFICATION_METHOD = 'none'
