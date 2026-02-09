from django import template

register = template.Library()


@register.filter
def dict_lookup(dictionary, key):
    """
    Custom template filter to lookup dictionary values by key.
    Usage: {{ mydict|dict_lookup:mykey }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)
