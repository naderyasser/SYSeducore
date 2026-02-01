"""
Enhanced Security Middleware for Production
"""

import logging
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """
    Add security headers to all responses
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Security headers
        if not settings.DEBUG:
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'SAMEORIGIN'
            response['X-XSS-Protection'] = '1; mode=block'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response


class RateLimitMiddleware:
    """
    Simple rate limiting middleware for critical endpoints
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.critical_paths = [
            '/api/attendance/scan',
            '/accounts/login',
            '/api/payments/',
        ]

    def __call__(self, request):
        # Check if rate limiting is enabled
        if not getattr(settings, 'RATELIMIT_ENABLE', True):
            return self.get_response(request)
        
        # Check if path is critical
        is_critical = any(request.path.startswith(path) for path in self.critical_paths)
        
        if is_critical and request.method == 'POST':
            # Get IP address
            ip = self.get_client_ip(request)
            cache_key = f'ratelimit:{ip}:{request.path}'
            
            # Check rate limit (max 60 requests per minute)
            count = cache.get(cache_key, 0)
            
            if count >= 60:
                logger.warning(f"Rate limit exceeded for IP {ip} on {request.path}")
                return HttpResponse('Rate limit exceeded. Please try again later.', status=429)
            
            # Increment counter
            cache.set(cache_key, count + 1, 60)
        
        return self.get_response(request)
    
    def get_client_ip(self, request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class RequestLoggingMiddleware:
    """
    Log all requests for security auditing
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Log request
        if not settings.DEBUG:
            logger.info(
                f"Request: {request.method} {request.path} "
                f"from {request.META.get('REMOTE_ADDR')} "
                f"User: {request.user if request.user.is_authenticated else 'Anonymous'}"
            )
        
        response = self.get_response(request)
        
        # Log suspicious responses
        if response.status_code >= 400:
            logger.warning(
                f"Response {response.status_code}: {request.method} {request.path} "
                f"User: {request.user if request.user.is_authenticated else 'Anonymous'}"
            )
        
        return response
