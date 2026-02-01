"""
Database Query Optimization Utilities
"""

from functools import wraps
from django.db import connection, reset_queries
from django.conf import settings
import time
import logging

logger = logging.getLogger(__name__)


def query_debugger(func):
    """
    Decorator to log database queries for performance monitoring
    Only active when DEBUG=True
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not settings.DEBUG:
            return func(*args, **kwargs)
        
        reset_queries()
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        
        query_count = len(connection.queries)
        duration = end - start
        
        if query_count > 10:
            logger.warning(
                f"{func.__name__} executed {query_count} queries in {duration:.2f}s"
            )
        
        return result
    return wrapper


def optimize_queryset(queryset, select_related=None, prefetch_related=None, only=None):
    """
    Helper to optimize queryset with common patterns
    
    Args:
        queryset: Base queryset
        select_related: Fields to select_related
        prefetch_related: Fields to prefetch_related
        only: Fields to include (only)
    
    Returns:
        Optimized queryset
    """
    if select_related:
        queryset = queryset.select_related(*select_related)
    
    if prefetch_related:
        queryset = queryset.prefetch_related(*prefetch_related)
    
    if only:
        queryset = queryset.only(*only)
    
    return queryset
