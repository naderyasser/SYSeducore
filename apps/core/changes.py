"""
«مين غيّر إيه» — before/after snapshots for the activity log.

An edit used to be logged as «تعديل بيانات المجموعة: X» and nothing else, so
the log could say *that* a price changed hands but never from what to what.
:func:`snapshot` reads a model instance's fields as the screen shows them
(choice labels, related names, نعم/لا) and :func:`describe_changes` turns two
snapshots into «السعر: من 300 إلى 350، …».
"""
from decimal import Decimal

EMPTY = '—'


def _display(instance, field):
    if field.choices:
        value = getattr(instance, field.attname)
        return str(dict(field.flatchoices).get(value, value)) if value not in (None, '') else EMPTY
    if field.many_to_one or field.one_to_one:
        related = getattr(instance, field.name, None)
        return str(related) if related is not None else EMPTY
    value = getattr(instance, field.attname, None)
    if value is None or value == '':
        return EMPTY
    if isinstance(value, bool):
        return 'نعم' if value else 'لا'
    if isinstance(value, Decimal):
        value = value.normalize()
        return f'{value:f}'
    if hasattr(value, 'strftime'):
        return value.strftime('%I:%M %p') if not hasattr(value, 'year') else value.isoformat()
    return str(value)


def snapshot(instance, names):
    """``{label: shown value}`` for ``names`` (model field names) on ``instance``."""
    shown = {}
    for name in names:
        try:
            field = instance._meta.get_field(name)
        except Exception:  # noqa: BLE001 — a form-only field has no model column
            continue
        if field.many_to_many:
            continue
        shown[str(field.verbose_name)] = _display(instance, field)
    return shown


def describe_changes(before, after):
    """«الخانة: من X إلى Y» for every label whose shown value changed."""
    return '، '.join(
        f'{label}: من {before.get(label, EMPTY)} إلى {value}'
        for label, value in after.items()
        if before.get(label, EMPTY) != value
    )
