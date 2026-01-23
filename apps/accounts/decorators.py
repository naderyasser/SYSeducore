from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied


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
    Decorator for views that checks if user is authenticated.
    """
    def check_teacher(user):
        if not user.is_authenticated:
            return False
        return True
    
    decorated_view = user_passes_test(check_teacher)(view_func)
    return decorated_view
