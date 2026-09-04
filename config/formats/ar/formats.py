"""
Number and date formats for ``ar-eg``.

Django ships an ``ar`` locale that sets ``DECIMAL_SEPARATOR = ","`` and
``THOUSAND_SEPARATOR = "."`` (the Maghreb/European convention). Egypt writes
money the other way round, so with the stock locale every fee on every screen
rendered as ``50,00`` and every empty balance as ``0,00`` — read by the desk
as "fifty something" rather than "fifty pounds". Worse, ``1250.00`` came out
as ``1.250,00``, where the leading group looks like a decimal point.

These overrides restore the separators used in Egypt and turn on grouping, so
amounts read as ``50.00`` and ``1,250.00``. ``FORMAT_MODULE_PATH`` in settings
points here.
"""
DECIMAL_SEPARATOR = "."
THOUSAND_SEPARATOR = ","
NUMBER_GROUPING = 3

DATE_FORMAT = "j F Y"
SHORT_DATE_FORMAT = "d/m/Y"
DATETIME_FORMAT = "j F Y - g:i A"
SHORT_DATETIME_FORMAT = "d/m/Y g:i A"
TIME_FORMAT = "g:i A"
YEAR_MONTH_FORMAT = "F Y"
MONTH_DAY_FORMAT = "j F"
