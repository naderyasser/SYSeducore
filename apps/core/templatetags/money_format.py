"""
One way to print money, for every screen.

Before this, an amount reached the page as a bare ``{{ group.standard_fee }}``.
Two things went wrong with that:

* ``LANGUAGE_CODE`` is ``ar-eg`` and Django's stock ``ar`` locale uses "," as
  the decimal point, so a 50-pound fee printed as ``50,00`` and an untouched
  balance as ``0,00``. (``config.formats`` now fixes the separator itself;
  these filters do not depend on it.)
* Every template appended a literal ``ج.م`` next to the number, so the trailing
  ``.00`` on a whole number stayed — ``50.00 ج.م`` where the desk says
  "50 ج.م".

``money`` renders the number, ``egp`` renders the number with the currency.
Both drop a zero fractional part, keep real piastres, and group thousands.
"""
from decimal import Decimal, DecimalException, ROUND_HALF_UP

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

CURRENCY_SUFFIX = 'ج.م'
#: U+00A0. A normal space lets a narrow phone cell drop "ج.م" onto its own
#: line, one row below the amount it belongs to.
NBSP = '\u00a0'
_CENT = Decimal('0.01')


def _as_decimal(value):
    """Coerce ``value`` to ``Decimal``, or ``None`` when it is not a number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        text = str(value).strip().replace(',', '')
    except Exception:  # pragma: no cover - str() of an exotic object
        return None
    if not text:
        return None
    try:
        return Decimal(text)
    except (DecimalException, ValueError):
        return None


@register.filter
def money(value, default='0'):
    """
    ``50`` for 50.00, ``1,250.50`` for 1250.5, ``default`` for nothing usable.

    Rounds to piastres, drops a zero fraction, groups thousands with ",".
    """
    amount = _as_decimal(value)
    if amount is None:
        return default
    amount = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    whole = amount.to_integral_value()
    if amount == whole:
        return f'{int(whole):,}'
    return f'{amount:,.2f}'


@register.filter
def egp(value, default='0'):
    """``money`` plus the currency: ``50 ج.م``.

    The space is a non-breaking one so the amount and its unit never wrap onto
    two lines inside a narrow table cell on a phone.
    """
    amount = money(value, default)
    if amount == default:
        # ``default`` is caller-supplied text; the formatted amount is not.
        amount = escape(default)
    return mark_safe(f'{amount}{NBSP}{CURRENCY_SUFFIX}')
