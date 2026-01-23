from django.utils import timezone
from django.contrib.auth import logout


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
