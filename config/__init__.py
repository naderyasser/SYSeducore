"""
Django project configuration package.
"""
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery not installed, skip for migrations
    pass
