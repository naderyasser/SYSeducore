"""
Shared helpers for the students app.

Kept deliberately small and dependency-free so views, api_views and forms
can all rely on the *same* parsing / validation rules:

* ``parse_money``            — user input → ``Decimal`` (never ``float``).
* ``normalize_financial_status`` — POST value → a value that really exists in
  ``StudentGroupEnrollment.FINANCIAL_STATUS_CHOICES``.
* ``normalize_phone``        — one canonical stored phone format (``01xxxxxxxxx``).
* ``enrollment_compatibility_errors`` — gender / education-stage compatibility
  between a student and a group (used by both the enrollment form and the
  enrollment API so they cannot drift apart).
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

__all__ = [
    'parse_money',
    'normalize_financial_status',
    'valid_financial_statuses',
    'normalize_phone',
    'enrollment_compatibility_errors',
]

MONEY_QUANT = Decimal('0.01')


def parse_money(value, default=None, min_value=Decimal('0')):
    """
    Parse user-supplied money into a ``Decimal`` suitable for a ``DecimalField``.

    Returns ``default`` for empty / non-numeric / infinite / out-of-range input
    instead of raising ``decimal.InvalidOperation`` deep inside the ORM.
    """
    if value is None:
        return default

    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        # float is never a money type — go through str() to avoid binary noise
        amount = Decimal(str(value))
    else:
        text = str(value).strip().replace(',', '').replace('٫', '.')
        if not text:
            return default
        try:
            amount = Decimal(text)
        except (InvalidOperation, ValueError, ArithmeticError):
            return default

    if not amount.is_finite():
        return default
    if min_value is not None and amount < min_value:
        return default

    try:
        return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ArithmeticError):
        return default


def valid_financial_statuses():
    """The set of financial-status values that actually exist in the model."""
    from .models import StudentGroupEnrollment
    return {value for value, _label in StudentGroupEnrollment.FINANCIAL_STATUS_CHOICES}


def normalize_financial_status(value, default='normal'):
    """
    Return ``value`` when it is a real ``financial_status`` choice, else ``default``.

    Django does not enforce ``choices`` at the database level, so every request
    path that writes ``financial_status`` must validate it explicitly — otherwise
    an arbitrary string (``exempt`` included) can be posted by anyone.
    """
    if value in valid_financial_statuses():
        return value
    return default


def normalize_phone(phone):
    """
    Canonical stored phone format for the whole app: ``01xxxxxxxxx``.

    Both ``StudentForm`` and ``StudentQuickForm`` use this, so a number saved
    from the quick-add dialog is byte-identical to the same number saved from
    the full form. ``WhatsAppService._format_phone_number`` turns the leading
    ``0`` into the ``20`` country code at send time.
    """
    if not phone:
        return phone

    phone = str(phone).replace(' ', '').replace('-', '').strip()
    if phone.startswith('+20'):
        phone = '0' + phone[3:]
    elif phone.startswith('0020'):
        phone = '0' + phone[4:]
    elif phone.startswith('20') and len(phone) == 12:
        phone = '0' + phone[2:]
    elif phone.startswith('+'):
        # keep non-Egyptian numbers intact rather than mangling them
        return phone

    if not phone.startswith('0') and len(phone) == 10:
        phone = '0' + phone
    return phone


def enrollment_compatibility_errors(student, group):
    """
    Arabic error messages for an incompatible student/group enrollment.

    Returns an empty list when the enrollment is allowed. Shared by
    ``StudentGroupEnrollmentForm.clean`` and the ``add_to_group`` API so the
    UI and the API enforce exactly the same rules.
    """
    errors = []
    if not student or not group:
        return errors

    if group.gender_type == 'male' and student.gender == 'female':
        errors.append('لا يمكن تسجيل طالبة في مجموعة مخصصة للبنين فقط')
    if group.gender_type == 'female' and student.gender == 'male':
        errors.append('لا يمكن تسجيل طالب في مجموعة مخصصة للبنات فقط')

    if group.education_stage and student.education_stage:
        if group.education_stage != student.education_stage:
            errors.append(
                f'المجموعة مخصصة لمرحلة "{group.get_education_stage_display()}" '
                f'والطالب في مرحلة "{student.get_education_stage_display()}"'
            )
    if group.education_year and student.education_year:
        if group.education_year != student.education_year:
            errors.append(
                f'المجموعة مخصصة للسنة "{group.get_education_year_display()}" '
                f'والطالب في السنة "{student.get_education_year_display()}"'
            )

    return errors
