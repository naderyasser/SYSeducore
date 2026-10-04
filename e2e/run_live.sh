#!/bin/sh
# Playwright smoke test of the LIVE site (https://sys.educore.software).
#
#   sh e2e/run_live.sh            # run from the repo root on the server
#   sh e2e/run_live.sh --buttons  # also click every button on every page
#
# Read-only: every POST/PUT/DELETE the pages send is intercepted in the browser
# and answered with a fake success, so nothing is ever written — the test only
# checks that the page sends the right data and updates itself.
#
# Logs in with a short-lived admin session created here and deleted on exit.
set -eu
cd "$(dirname "$0")/.."
command -v uptime >/dev/null && uptime
TMP=$(mktemp)
cleanup() {
    KEY=$(python3 -c "import json;print(json.load(open('$TMP'))['key'])" 2>/dev/null || true)
    if [ -n "$KEY" ]; then
        docker compose exec -T web python manage.py shell -c \
            "from django.contrib.sessions.models import Session; Session.objects.filter(session_key='$KEY').delete()" \
            >/dev/null 2>&1 || true
    fi
    rm -f "$TMP"
}
trap cleanup EXIT INT TERM

docker compose exec -T web python manage.py shell -c "
import json
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.sessions.backends.db import SessionStore
from apps.attendance.models import Attendance
from apps.payments.models import TeacherSettlement
from apps.students.models import Student
from apps.teachers.models import GroupCycle
u = get_user_model().objects.filter(is_superuser=True).first()
s = SessionStore(); s[SESSION_KEY] = str(u.pk); s[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
s[HASH_SESSION_KEY] = u.get_session_auth_hash(); s.set_expiry(1800); s.create()
cyc = GroupCycle.objects.filter(closed_on__isnull=True, started_on__isnull=False, sessions__isnull=False).order_by('-cycle_id').first()
exc = Attendance.objects.filter(status='exception').select_related('session').order_by('-session__session_date').first()
st = Student.objects.filter(payments__isnull=False, group_enrollments__is_active=True).order_by('pk').first()
print(json.dumps({
    'cookie': settings.SESSION_COOKIE_NAME, 'key': s.session_key,
    'group_id': cyc.group_id, 'student_id': st.pk, 'student_code': st.student_code,
    'settlement_id': getattr(TeacherSettlement.objects.order_by('-pk').first(), 'pk', None),
    'exc_group': exc.session.group_id if exc else None,
    'exc_date': exc.session.session_date.isoformat() if exc else None,
}))
" 2>/dev/null | tail -1 > "$TMP"

if [ "${1:-}" = "--buttons" ]; then
    nice -n 19 python3 e2e/live_buttons.py "$TMP"
else
    nice -n 19 python3 e2e/live_smoke.py "$TMP"
fi
