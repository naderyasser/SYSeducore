"""Response headers every page should carry."""
from django.utils.cache import add_never_cache_headers

# The scanner reads QR codes with the camera, so this site keeps it; nothing
# on it needs the microphone, location or payment APIs.
PERMISSIONS_POLICY = 'camera=(self), microphone=(), geolocation=(), payment=(), usb=()'


class SecurityHeadersMiddleware:
    """
    * ``Permissions-Policy`` on every response.
    * Pages rendered for a signed-in user are never stored: without it the
      browser's back button, after "تسجيل الخروج", showed the student and
      payment pages it had cached. Views that already chose a Cache-Control
      (downloads, the service worker) keep theirs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault('Permissions-Policy', PERMISSIONS_POLICY)
        user = getattr(request, 'user', None)
        if (
            user is not None and user.is_authenticated
            and response.get('Content-Type', '').startswith('text/html')
            and not response.has_header('Cache-Control')
        ):
            add_never_cache_headers(response)
            response['Cache-Control'] += ', private'
        return response
