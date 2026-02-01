"""
Custom template tags and filters for notifications app
"""

from django import template

register = template.Library()


@register.filter
def multiply(value, arg):
    """
    Multiply a value by argument
    
    Usage: {{ value|multiply:20 }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def divide(value, arg):
    """
    Divide a value by argument
    
    Usage: {{ value|divide:2 }}
    """
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0


@register.filter
def percentage(value, total):
    """
    Calculate percentage
    
    Usage: {{ count|percentage:total }}
    """
    try:
        if total == 0:
            return 0
        return (float(value) / float(total)) * 100
    except (ValueError, TypeError):
        return 0


@register.filter
def add_class(field, css_class):
    """
    Add CSS class to form field
    
    Usage: {{ field|add_class:"form-control" }}
    """
    return field.as_widget(attrs={"class": css_class})
