from django.conf import settings

from apps.core import education


def notification_settings(request):
    return {
        'NOTIFICATION_METHOD': getattr(settings, 'NOTIFICATION_METHOD', 'none'),
    }


def education_taxonomy(request):
    """
    Stage/year taxonomy for every template, so no page hard-codes a year list.

    ``EDUCATION_STAGE_YEARS`` is handed to the template as a plain dict and
    rendered by base.html through Django's ``|json_script`` filter, which owns
    the escaping. An earlier version serialised it here and wrapped the result
    in ``mark_safe`` with hand-rolled ``<``/``&`` escaping — correct, but it put
    an XSS-shaped construct in the codebase for a job the framework already
    does properly, and bandit flagged it (B308/B703) on every run.

    It is emitted globally rather than per-view because four separate forms
    need it and they must not drift apart again — that drift is exactly how
    إعدادي came to offer six years on one screen and three on another.
    """
    return {
        'EDUCATION_STAGE_CHOICES': education.EDUCATION_STAGE_CHOICES,
        'EDUCATION_YEAR_CHOICES_SHORT': education.YEAR_CHOICES_SHORT,
        'EDUCATION_YEAR_CHOICES_GRADE': education.YEAR_CHOICES_GRADE,
        'EDUCATION_STAGE_YEARS': education.stage_years_map(),
        'EDUCATION_NO_YEAR_LABEL': education.NO_YEAR_LABEL,
    }


def feature_notice(request):
    """
    "جديد" badges on the features of the latest update, and a banner saying
    they stop on ``FEATURE_NOTICE_DEADLINE`` unless the update is paid for.

    Admins only — the centre's owner settles the bill; the desk staff are not
    part of it. Unset the variable in .env (and recreate the web container)
    and every badge and the banner disappear.
    """
    raw = getattr(settings, 'FEATURE_NOTICE_DEADLINE', '')
    user = getattr(request, 'user', None)
    if not raw or user is None or not user.is_authenticated or not user.is_admin():
        return {}
    from datetime import datetime
    from django.utils import timezone
    try:
        deadline = datetime.fromisoformat(raw)
    except ValueError:
        return {}
    if timezone.is_naive(deadline):
        deadline = timezone.make_aware(deadline)
    if deadline <= timezone.now():
        return {}
    return {'feature_notice': {'deadline': deadline}}
