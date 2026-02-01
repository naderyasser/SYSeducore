"""
Test settings for SYSeducore project.
Uses SQLite for faster testing without PostgreSQL.
"""
from .settings import *

# Add testserver to ALLOWED_HOSTS for testing
ALLOWED_HOSTS = list(ALLOWED_HOSTS) + ['testserver', 'localhost', '127.0.0.1']

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
