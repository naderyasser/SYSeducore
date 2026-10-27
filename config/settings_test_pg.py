"""
Test settings on PostgreSQL — same as ``settings_test`` but against the real
engine, in a throw-away ``test_*`` database Django creates and drops.

SQLite let a ``SELECT … FOR UPDATE`` over an outer join through (Postgres
rejects it), and that bug reached the desk in Oct 2026. Run before deploys
that touch locking or queries:

    docker compose exec -T web nice -n 19 python manage.py test --settings=config.settings_test_pg apps tests
"""
from .settings_test import *  # noqa: F401,F403
from .settings import DATABASES as _PROD_DATABASES

DATABASES = {'default': dict(_PROD_DATABASES['default'])}
DATABASES['default']['TEST'] = {'NAME': 'test_educore_pg'}
CELERY_BROKER_URL = 'memory://'
WAPILOT_API_TOKEN = ''
WAPILOT_INSTANCE_ID = ''
