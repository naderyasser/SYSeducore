"""
Authentication / authorization decorators.

Two families of decorators live here:

* HTML decorators (``admin_required``, ``supervisor_required``,
  ``teacher_required``) — an anonymous visitor is redirected to the login
  page (the normal browser flow), an *authenticated* visitor without the
  required role gets a real **HTTP 403**. They never redirect an
  authenticated user back to the login page: that used to bounce straight
  to the dashboard again and looked like a silent no-op.

* JSON decorators (``ajax_login_required``, ``ajax_admin_required``,
  ``ajax_supervisor_required``) — always return JSON so a ``fetch()``
  caller can safely call ``response.json()``: 401 when anonymous,
  403 when the role is wrong.

All role decorators enforce authentication themselves, so a view only ever
needs one of them; they are also safe to stack under an existing
``@login_required`` (the outer decorator handles the anonymous case first,
so there is no double redirect).

``ratelimit_key`` is the ``key=`` callable for ``django_ratelimit``: it
returns the *real* client IP instead of the reverse-proxy address.
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

__all__ = [
    'ajax_login_required',
    'admin_required',
    'supervisor_required',
    'teacher_required',
    'ajax_admin_required',
    'ajax_supervisor_required',
    'ratelimit_key',
    'get_client_ip',
]


# --- Role sets -------------------------------------------------------------

ADMIN_ROLES = ('admin',)
SUPERVISOR_ROLES = ('admin', 'supervisor')
TEACHER_ROLES = ('admin', 'supervisor', 'teacher')

# --- Arabic user-facing messages ------------------------------------------

SESSION_EXPIRED_MESSAGE = 'الجلسة منتهية، يرجى تسجيل الدخول'
PERMISSION_DENIED_MESSAGE = 'ليس لديك صلاحية للقيام بهذا الإجراء'


# --- Client IP -------------------------------------------------------------

def get_client_ip(request):
    """
    Return the real client IP.

    Behind nginx ``REMOTE_ADDR`` is always the proxy container address.
    ``X-Real-IP`` is set by nginx itself to ``$remote_addr`` on every
    request (nginx.conf), which *overwrites* any value a client tries to
    send — unlike ``X-Forwarded-For``, which nginx only *appends* to
    (``$proxy_add_x_forwarded_for``), so a client-supplied leftmost entry
    survives untouched and is trivially spoofable. Prefer ``X-Real-IP``
    for that reason and only fall back to the (spoofable) leftmost
    ``X-Forwarded-For`` entry when it is absent, e.g. in tests that talk
    to the app directly without going through nginx.
    """
    if request is None:
        return 'unknown'

    meta = getattr(request, 'META', None) or {}
    real_ip = meta.get('HTTP_X_REAL_IP')
    if real_ip and real_ip.strip():
        return real_ip.strip()
    forwarded_for = meta.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        client_ip = forwarded_for.split(',')[0].strip()
        if client_ip:
            return client_ip
    return meta.get('REMOTE_ADDR') or 'unknown'


def ratelimit_key(group, request):
    """
    ``key=`` callable for ``django_ratelimit``.

    ``key='ip'`` reads ``REMOTE_ADDR``, which behind the proxy is a single
    shared address — the whole centre would share one bucket. This keys the
    bucket on the real client IP instead.
    """
    return get_client_ip(request)


# --- Shared helpers --------------------------------------------------------

def _is_authenticated(request):
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated)


def _has_role(request, allowed_roles):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'role', None) in allowed_roles


def _role_required(allowed_roles):
    """Build an HTML role decorator: redirect anonymous, 403 wrong role."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not _is_authenticated(request):
                return redirect_to_login(request.get_full_path())
            if not _has_role(request, allowed_roles):
                raise PermissionDenied(PERMISSION_DENIED_MESSAGE)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def _ajax_role_required(allowed_roles):
    """Build a JSON role decorator: 401 anonymous, 403 wrong role."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not _is_authenticated(request):
                return JsonResponse(
                    {'success': False, 'message': SESSION_EXPIRED_MESSAGE},
                    status=401,
                )
            if not _has_role(request, allowed_roles):
                return JsonResponse(
                    {'success': False, 'message': PERMISSION_DENIED_MESSAGE},
                    status=403,
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# --- Public decorators -----------------------------------------------------

def ajax_login_required(view_func):
    """
    Like ``@login_required`` but returns JSON 401 instead of redirecting.
    Use on API views called via ``fetch()``.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not _is_authenticated(request):
            return JsonResponse(
                {'success': False, 'message': SESSION_EXPIRED_MESSAGE},
                status=401,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


#: HTML view, admin only. Anonymous → login redirect, wrong role → 403.
admin_required = _role_required(ADMIN_ROLES)

#: HTML view, admin or supervisor. Anonymous → login redirect, else 403.
supervisor_required = _role_required(SUPERVISOR_ROLES)

#: HTML view, admin / supervisor / teacher. Anonymous → login redirect, else 403.
teacher_required = _role_required(TEACHER_ROLES)

#: JSON view, admin only. Anonymous → 401 JSON, wrong role → 403 JSON.
ajax_admin_required = _ajax_role_required(ADMIN_ROLES)

#: JSON view, admin or supervisor. Anonymous → 401 JSON, wrong role → 403 JSON.
ajax_supervisor_required = _ajax_role_required(SUPERVISOR_ROLES)
