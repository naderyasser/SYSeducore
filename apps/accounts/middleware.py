from django.utils import timezone
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
    Middleware to handle session timeout.
    Logs out users after 1 hour of inactivity.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated:
            # Check last activity
            last_activity = request.session.get('last_activity')
            
            if last_activity:
                elapsed = timezone.now().timestamp() - last_activity
                if elapsed > 3600:  # 1 hour
                    logout(request)
                    request.session.flush()
            
            request.session['last_activity'] = timezone.now().timestamp()
        
        response = self.get_response(request)
        return response
