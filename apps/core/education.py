"""
The single source of truth for "المرحلة الدراسية" and "السنة الدراسية".

Three independent copies of these choices used to live in
``apps.students.models.Student``, ``apps.teachers.models.Group`` and
``apps.teachers.models.Subject``, with a fourth hard-coded list of ``<option>``
tags in each of four templates. Nothing kept them in step, which is how
"إعدادي" came to offer six academic years in one form and three in another:
``teachers/groups/form.html`` carried a real ``STAGE_YEAR_MAP`` while
``students/form.html`` only tagged years 4-6 as ``data-primary-only`` and hid
them with ``style.display = 'none'`` — a rule browsers are free to ignore on
``<option>`` elements, and Safari/iOS does exactly that.

Everything now derives from :data:`STAGE_YEARS` below: model choices, form
validation, and (via ``config.context_processors.education_taxonomy``) the
JSON map the front-end rebuilds its year dropdown from.

A stage that maps to an empty year list — تأسيس and كورسات — has no academic
year at all: the field is emptied server-side and hidden client-side rather
than left showing a stale value from a previously selected stage.
"""

#: Stage keys, in display order. ``foundation``/``courses`` are year-less.
STAGE_PRIMARY = 'primary'
STAGE_PREPARATORY = 'preparatory'
STAGE_SECONDARY = 'secondary'
STAGE_FOUNDATION = 'foundation'
STAGE_COURSES = 'courses'

EDUCATION_STAGE_CHOICES = [
    (STAGE_PRIMARY, 'ابتدائي'),
    (STAGE_PREPARATORY, 'إعدادي'),
    (STAGE_SECONDARY, 'ثانوي'),
    (STAGE_FOUNDATION, 'تأسيس'),
    (STAGE_COURSES, 'كورسات'),
]

#: Which years each stage actually has. Primary runs six years; preparatory
#: and secondary run three each; تأسيس and كورسات have none.
STAGE_YEARS = {
    STAGE_PRIMARY: ['1', '2', '3', '4', '5', '6'],
    STAGE_PREPARATORY: ['1', '2', '3'],
    STAGE_SECONDARY: ['1', '2', '3'],
    STAGE_FOUNDATION: [],
    STAGE_COURSES: [],
}

#: Stages with no academic year. Selecting one blanks ``education_year``.
STAGES_WITHOUT_YEARS = frozenset(
    stage for stage, years in STAGE_YEARS.items() if not years
)

#: Shown when a year-less stage is selected, in place of the year dropdown.
NO_YEAR_LABEL = 'لا يوجد'

# Two label sets, because the two models have always displayed years
# differently and changing either would rewrite text the desk staff read on
# every screen: Student says "الأول", Group says "الصف الأول".
YEAR_CHOICES_SHORT = [
    ('1', 'الأول'),
    ('2', 'الثاني'),
    ('3', 'الثالث'),
    ('4', 'الرابع'),
    ('5', 'الخامس'),
    ('6', 'السادس'),
]

YEAR_CHOICES_GRADE = [
    ('1', 'الصف الأول'),
    ('2', 'الصف الثاني'),
    ('3', 'الصف الثالث'),
    ('4', 'الصف الرابع'),
    ('5', 'الصف الخامس'),
    ('6', 'الصف السادس'),
]


def years_for_stage(stage):
    """
    The year keys valid for ``stage``.

    An unknown or empty stage returns *every* year rather than none: a filter
    with no stage chosen must not silently drop rows, and a legacy row whose
    stage predates this table must stay editable.
    """
    if not stage:
        return [year for year, _ in YEAR_CHOICES_SHORT]
    return list(STAGE_YEARS.get(stage, [year for year, _ in YEAR_CHOICES_SHORT]))


def stage_has_years(stage):
    """False for تأسيس / كورسات — the year field does not apply at all."""
    return stage not in STAGES_WITHOUT_YEARS


def normalize_stage_year(stage, year):
    """
    Coerce a (stage, year) pair to a consistent one, returning the year to
    store.

    * A year-less stage stores ``''`` whatever the browser posted — a user who
      picks إعدادي/الثالث and then switches to تأسيس must not leave "3" behind.
    * A year that does not exist in the chosen stage stores ``''`` too, so a
      stale "السادس" from ابتدائي cannot survive a switch to إعدادي.

    Returned rather than raised: the year field is optional everywhere, and
    rejecting the whole form over a dropdown the user can no longer even see
    would block a legitimate save.
    """
    year = (year or '').strip()
    if not stage or not year:
        return ''
    if not stage_has_years(stage):
        return ''
    if year not in STAGE_YEARS.get(stage, []):
        return ''
    return year


def stage_years_map():
    """
    The map the front-end rebuilds its year ``<select>`` from, as plain data:
    ``{stage: [{'value': '1', 'label': 'الأول'}, ...]}``.

    Emitted into every page by ``config.context_processors.education_taxonomy``
    so no template hard-codes a year list again.
    """
    short = dict(YEAR_CHOICES_SHORT)
    grade = dict(YEAR_CHOICES_GRADE)
    return {
        stage: {
            'short': [{'value': y, 'label': short[y]} for y in years],
            'grade': [{'value': y, 'label': grade[y]} for y in years],
        }
        for stage, years in STAGE_YEARS.items()
    }
