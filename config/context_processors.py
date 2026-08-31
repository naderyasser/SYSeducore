import json

from django.conf import settings
from django.utils.safestring import mark_safe

from apps.core import education


def notification_settings(request):
    return {
        'NOTIFICATION_METHOD': getattr(settings, 'NOTIFICATION_METHOD', 'none'),
    }


def education_taxonomy(request):
    """
    Stage/year taxonomy for every template, so no page hard-codes a year list.

    ``EDUCATION_STAGE_YEARS_JSON`` is the map ``static/js/utils/education-stage-year.js``
    rebuilds the "السنة الدراسية" dropdown from. It is serialised here rather
    than through ``|json_script`` in each template because four separate pages
    need it and they must not drift apart again — that drift is exactly how
    إعدادي came to offer six years on one screen and three on another.

    ``json.dumps`` with ``ensure_ascii=False`` keeps the Arabic labels
    readable in view-source; the ``<`` escaping below is what makes the result
    safe to drop straight into a ``<script>`` block (a label can never contain
    ``</script>`` today, but the guard costs nothing and does not depend on
    that staying true).
    """
    payload = json.dumps(education.stage_years_map(), ensure_ascii=False)
    payload = payload.replace('<', '\\u003c').replace('&', '\\u0026')
    return {
        'EDUCATION_STAGE_CHOICES': education.EDUCATION_STAGE_CHOICES,
        'EDUCATION_YEAR_CHOICES_SHORT': education.YEAR_CHOICES_SHORT,
        'EDUCATION_YEAR_CHOICES_GRADE': education.YEAR_CHOICES_GRADE,
        'EDUCATION_STAGE_YEARS_JSON': mark_safe(payload),
        'EDUCATION_NO_YEAR_LABEL': education.NO_YEAR_LABEL,
    }
