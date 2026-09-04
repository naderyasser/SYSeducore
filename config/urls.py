"""
URL configuration for attendance_system project.
"""
import logging

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from django.shortcuts import render
from django.template import TemplateDoesNotExist
from django.views.generic import RedirectView

from config.health import health_check

logger = logging.getLogger(__name__)


# --- QUAL-07: project-level error handlers -----------------------------------
# These render templates/403.html, 404.html and 500.html when those templates
# exist, and otherwise fall back to a self-contained Arabic RTL response. The
# fallback must never raise, so template rendering is wrapped defensively: a 500
# page that itself explodes would hide the original error.
#
# 403 was missing here, so a teacher who opened a screen they are not allowed
# to see got Django's built-in page: "403 Forbidden", in English, unstyled, no
# way back. The Arabic message the permission check actually raises
# ("ليس لديك صلاحية للقيام بهذا الإجراء") was thrown away with it.

_ERROR_PAGE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:#f6f7fb;color:#22252a;
margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center}}
.box{{background:#fff;padding:2.5rem 3rem;border-radius:14px;box-shadow:0 6px 24px rgba(0,0,0,.08);max-width:32rem}}
h1{{font-size:3.5rem;margin:0;color:#4054b2}}
h2{{font-size:1.25rem;margin:.5rem 0 1rem}}
p{{color:#666;margin:0 0 1.5rem}}
a{{display:inline-block;background:#4054b2;color:#fff;text-decoration:none;padding:.6rem 1.4rem;border-radius:8px}}
</style>
</head>
<body>
<div class="box">
<h1>{code}</h1>
<h2>{title}</h2>
<p>{message}</p>
<a href="/">العودة إلى الصفحة الرئيسية</a>
</div>
</body>
</html>
"""


def _fallback_error_response(code, title, message):
    return HttpResponse(
        _ERROR_PAGE.format(code=code, title=title, message=message),
        status=code,
        content_type='text/html; charset=utf-8',
    )


def _render_or_fallback(request, template_name, code, title, message):
    try:
        return render(request, template_name, status=code)
    except TemplateDoesNotExist:
        pass  # no project template yet - use the built-in page below
    except Exception:  # noqa: BLE001 - the error page must never raise
        logger.exception('Error handler could not render %s', template_name)
    return _fallback_error_response(code, title, message)


def error_403(request, exception=None):
    """
    Arabic 403 page. Uses templates/403.html when that template exists.

    The message carried by the ``PermissionDenied`` is preferred over the
    generic line: the decorators raise a sentence written for the person
    reading it, and repeating it here is more useful than "access denied".
    """
    message = str(exception) if exception else ''
    if not message or message == 'Permission denied':
        message = 'هذه الصفحة متاحة لصلاحية أعلى من صلاحيتك. ارجع للصفحة الرئيسية أو اطلب من المدير فتحها لك.'
    return _render_or_fallback(
        request,
        '403.html',
        403,
        'لا تملك صلاحية الدخول',
        message,
    )


def error_404(request, exception=None):
    """Arabic 404 page. Uses templates/404.html when that template exists."""
    return _render_or_fallback(
        request,
        '404.html',
        404,
        'الصفحة غير موجودة',
        'الرابط الذي طلبته غير متاح أو تم نقله.',
    )


def error_500(request):
    """Arabic 500 page. Uses templates/500.html when that template exists."""
    return _render_or_fallback(
        request,
        '500.html',
        500,
        'خطأ في الخادم',
        'حدث خطأ غير متوقع. تم تسجيل المشكلة وسيتم مراجعتها.',
    )


handler403 = 'config.urls.error_403'
handler404 = 'config.urls.error_404'
handler500 = 'config.urls.error_500'


urlpatterns = [
    path('admin/', admin.site.urls),

    # Infrastructure health probe (nginx proxies /health/, no auth, no DB access)
    path('health/', health_check, name='health_check'),

    # Redirect root to dashboard
    path('', RedirectView.as_view(url='/reports/', permanent=False)),
    path('dashboard/', RedirectView.as_view(url='/reports/', permanent=False)),
    
    # App URLs
    path('accounts/', include('apps.accounts.urls')),
    path('students/', include('apps.students.urls')),
    path('teachers/', include('apps.teachers.urls')),
    path('attendance/', include('apps.attendance.urls')),
    path('payments/', include('apps.payments.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('reports/', include('apps.reports.urls')),
    
    # API endpoints
    path('api/', include([
        path('attendance/', include('apps.attendance.api_urls')),
        path('payments/', include('apps.payments.api_urls')),
        path('groups/filter/', include('apps.teachers.api_filter_urls')),
    ])),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
