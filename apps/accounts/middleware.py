import time

from django.contrib.auth import logout
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.conf import settings


class SystemLockoutMiddleware:
    """
    Blocks ALL access to the system and shows a 'system closed' page.
    Activated when SYSTEM_LOCKOUT = True in settings.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'SYSTEM_LOCKOUT', False):
            # Allow static files to load for the lockout page styling
            if request.path.startswith('/static/'):
                return self.get_response(request)
            # Logout any authenticated user
            if request.user.is_authenticated:
                logout(request)
            html = render_to_string('system_closed.html')
            return HttpResponse(html, status=503)
        return self.get_response(request)


class SessionTimeoutMiddleware:
    """
    Single source of truth for the idle timeout.

    ``SESSION_SAVE_EVERY_REQUEST`` is off, so the session cookie/DB row is not
    refreshed automatically; this middleware slides the expiry forward while
    the user is active and signs them out once they have been idle for
    ``SESSION_IDLE_TIMEOUT`` seconds (defaults to ``SESSION_COOKIE_AGE``).

    It is deliberately cheap:

    * static / media requests are skipped before ``request.user`` is even
      evaluated (that attribute is lazy and hits the DB);
    * the session is only written when the stored timestamp has actually
      moved by more than ``SESSION_ACTIVITY_GRANULARITY`` seconds, instead of
      on every single request.
    """

    SESSION_KEY = 'last_activity'
    #: Don't rewrite the session more often than this (seconds).
    DEFAULT_GRANULARITY = 60

    def __init__(self, get_response):
        self.get_response = get_response
        self.idle_timeout = getattr(
            settings,
            'SESSION_IDLE_TIMEOUT',
            getattr(settings, 'SESSION_COOKIE_AGE', 3600),
        )
        self.granularity = getattr(
            settings, 'SESSION_ACTIVITY_GRANULARITY', self.DEFAULT_GRANULARITY
        )
        self.skip_prefixes = tuple(
            prefix for prefix in (
                getattr(settings, 'STATIC_URL', None),
                getattr(settings, 'MEDIA_URL', None),
            ) if prefix
        )

    def _should_skip(self, request):
        path = request.path
        if self.skip_prefixes and path.startswith(self.skip_prefixes):
            return True
        # Service worker / manifest / favicon polling should not keep a
        # session alive either, and never needs a session write.
        return path in ('/favicon.ico', '/sw.js', '/manifest.json')

    def __call__(self, request):
        if not self._should_skip(request):
            self._touch(request)
        return self.get_response(request)

    def _touch(self, request):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return

        session = request.session
        now = time.time()
        last_activity = session.get(self.SESSION_KEY)

        if last_activity:
            try:
                idle_for = now - float(last_activity)
            except (TypeError, ValueError):
                idle_for = 0
            if idle_for > self.idle_timeout:
                logout(request)
                request.session.flush()
                return
            if idle_for < self.granularity:
                # Recent enough — skip the session write entirely.
                return

        # Writing the timestamp marks the session modified, which slides the
        # cookie/DB expiry forward for an active user.
        session[self.SESSION_KEY] = now
