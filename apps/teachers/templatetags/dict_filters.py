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


#: Attendance-grid cell state → (glyph, CSS class). Shared by the group
#: detail page and the printable roster so the two stay visually consistent.
CELL_GLYPHS = {
    'present': ('✓', 'present'),
    'late': ('م', 'late'),
    'absent': ('✗', 'absent'),
    'exception': ('س', 'exception'),
    'no_record': ('—', 'no_record'),
    'cancelled': ('//', 'cancelled'),
    'not_enrolled': ('', 'not_enrolled'),
    'unrecorded': ('', 'unrecorded'),
}


@register.filter
def cell_glyph(state):
    """The single character shown in one attendance-grid cell."""
    return CELL_GLYPHS.get(state, ('؟', 'unknown'))[0]


@register.filter
def cell_class(state):
    """The CSS class for one attendance-grid cell."""
    return CELL_GLYPHS.get(state, ('؟', 'unknown'))[1]
