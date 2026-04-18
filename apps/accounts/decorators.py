from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse


def ajax_login_required(view_func):
    """
    Like @login_required but returns JSON 401 instead of redirecting.
    Use on API views called via fetch().
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'success': False, 'message': 'الجلسة منتهية، يرجى تسجيل الدخول'},
                status=401,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    """
    Decorator for views that checks if user is admin.
    """
    def check_admin(user):
        if not user.is_authenticated:
            return False
        return user.role == 'admin'
    
    decorated_view = user_passes_test(check_admin)(view_func)
    return decorated_view


def supervisor_required(view_func):
    """
    Decorator for views that checks if user is supervisor or admin.
    """
    def check_supervisor(user):
        if not user.is_authenticated:
            return False
        return user.role in ['admin', 'supervisor']
    
    decorated_view = user_passes_test(check_supervisor)(view_func)
    return decorated_view


def teacher_required(view_func):
    """
    Decorator for views that checks if user is a teacher, supervisor, or admin.
    """
    def check_teacher(user):
        if not user.is_authenticated:
            return False
        return user.role in ['teacher', 'admin', 'supervisor']
    
    decorated_view = user_passes_test(check_teacher)(view_func)
    return decorated_view
