"""
Arithmetic filters for the report templates.

Two things used to be wrong here (FE-04):

1. The addition filter was called ``add``, which **shadows Django's built-in
   ``add``**. Any template doing ``{% load math_filters %}`` silently swapped
   integer/string concatenation for float arithmetic — ``{{ "a"|add:"b" }}``
   started returning ``0`` and ``{{ 1|add:2 }}`` started returning ``3.0``.
   It is called ``add_num`` now; the built-in ``add`` is left alone.
2. Every filter coerced ``Decimal`` money to ``float`` (re-introducing binary
   rounding into the amounts the reports show) and only caught ``ValueError``,
   so a ``None`` value — a missing aggregate, an empty column — raised
   ``TypeError`` mid-render and 500'd the page.

All four filters now do exact ``Decimal`` arithmetic where both operands are
exact, fall back to ``float`` only for genuine floats, and return ``0`` for
anything unusable instead of raising.
"""
from decimal import Decimal, DecimalException

from django import template

register = template.Library()


def _to_number(value):
    """
    Coerce ``value`` to ``Decimal`` (exact) or ``float``, or ``None``.

    ``Decimal`` is preserved so money keeps its exact value; only an actual
    ``float`` input stays a float.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return value
    try:
        return Decimal(str(value).strip())
    except (DecimalException, ValueError, TypeError, AttributeError):
        return None


def _pair(value, arg):
    """Return both operands as numbers of a compatible type, or ``None``."""
    left = _to_number(value)
    right = _to_number(arg)
    if left is None or right is None:
        return None
    # Decimal and float do not mix; promote to float only if one already is.
    if isinstance(left, float) or isinstance(right, float):
        return float(left), float(right)
    return left, right


@register.filter
def div(value, arg):
    """Divide value by arg. Returns 0 on bad input or division by zero."""
    pair = _pair(value, arg)
    if pair is None:
        return 0
    left, right = pair
    if not right:
        return 0
    try:
        return left / right
    except (ZeroDivisionError, ArithmeticError):
        return 0


@register.filter
def mul(value, arg):
    """Multiply value by arg. Returns 0 on bad input."""
    pair = _pair(value, arg)
    if pair is None:
        return 0
    try:
        return pair[0] * pair[1]
    except ArithmeticError:
        return 0


@register.filter
def sub(value, arg):
    """Subtract arg from value. Returns 0 on bad input."""
    pair = _pair(value, arg)
    if pair is None:
        return 0
    try:
        return pair[0] - pair[1]
    except ArithmeticError:
        return 0


@register.filter
def add_num(value, arg):
    """
    Numeric addition.

    Deliberately **not** called ``add``: that is a Django built-in and
    registering it here silently overrode it for every template that loads
    this library.
    """
    pair = _pair(value, arg)
    if pair is None:
        return 0
    try:
        return pair[0] + pair[1]
    except ArithmeticError:
        return 0
