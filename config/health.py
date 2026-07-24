"""
Dependency-free health endpoint (OPS-06).

nginx proxies ``/health/`` to Django and the deploy workflow smoke-tests the same
URL, but no such route existed. This view answers with a static 200 JSON payload:
it never touches the database, Redis or the session store, so it stays a *liveness*
probe and does not flap when a backing service is briefly unavailable.

It requires no authentication by design - it exposes nothing beyond the fact that
the WSGI worker is alive and able to render a response.
"""

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe


@csrf_exempt
@never_cache
@require_safe
def health_check(request):
    """Return 200 + JSON without touching any external dependency."""
    response = JsonResponse(
        {
            'status': 'ok',
            'service': 'syseducore',
        },
        status=200,
    )
    # Probes should never be cached by nginx or an intermediate proxy.
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response
