"""قفل مميزات آخر تحديث لحد ما تكلفته تتدفع (2026-09-28).

Before ``FEATURE_NOTICE_DEADLINE`` the features carry a «جديد» badge and admins
see the banner (``context_processors.feature_notice``). After it, unless
``FEATURE_UPDATE_PAID`` is true, they are locked: the badge becomes a grey
«مقفولة» chip, the marked sections turn grey and a click shows the wallet
number (``FEATURE_UPDATE_WALLET``), and the endpoints that exist only for these
features refuse on the server as well — a grey button alone is not a lock.

Unlocking is one line in .env: ``FEATURE_UPDATE_PAID=true`` + recreate web.
Nothing is deleted either way.
"""

from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone


def message():
    wallet = getattr(settings, 'FEATURE_UPDATE_WALLET', '')
    return (
        'الميزة دي من التحديث الأخير ومقفولة لحد سداد تكلفته. '
        f'حوّل على المحفظة {wallet} وأول ما التحويل يوصل هتتفتح على طول.'
    )


def is_locked():
    if getattr(settings, 'FEATURE_UPDATE_PAID', False):
        return False
    raw = getattr(settings, 'FEATURE_NOTICE_DEADLINE', '')
    if not raw:
        return False
    from datetime import datetime

    try:
        deadline = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if timezone.is_naive(deadline):
        deadline = timezone.make_aware(deadline)
    return deadline <= timezone.now()


def locked_feature(view):
    """Refuse a view that exists only for the locked update."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_locked():
            return view(request, *args, **kwargs)
        wants_json = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'json' in (
            request.headers.get('accept') or ''
        )
        if wants_json:
            return JsonResponse({'success': False, 'error': message(), 'code': 'feature_locked'}, status=403)
        return render(
            request,
            'includes/feature_locked.html',
            {'lock_message': message(), 'wallet': getattr(settings, 'FEATURE_UPDATE_WALLET', '')},
            status=403,
        )

    return wrapper
