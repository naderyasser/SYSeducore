"""
Guards for what the screens actually put in front of a user.

Three faults are covered, all of which shipped and all of which are invisible
to a normal view test because the page still returns 200:

1. ``{# … #}`` is a *single-line* comment in the Django template language. A
   multi-line one is not a comment at all: the first line is discarded and the
   rest is rendered as page text. Fourteen of them had accumulated, and the
   groups directory showed a developer note about teacher search to every user
   who opened it.
2. ``LANGUAGE_CODE`` is ``ar-eg`` and Django's stock ``ar`` locale uses "," as
   the decimal point, so every fee printed as ``50,00`` and every settled
   balance as ``0,00``.
3. Money was assembled ad hoc in each template as ``{{ value }} ج.م``, which
   kept the trailing ``.00`` on whole pounds.
"""
import re
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase

from apps.core.templatetags.money_format import egp, money

TEMPLATE_ROOT = Path(settings.BASE_DIR) / 'templates'

# ``{#`` … first ``#}``. A match containing a newline is a comment the
# template engine will not treat as one.
COMMENT = re.compile(r'\{#.*?#\}', re.S)


class TemplateCommentsTests(SimpleTestCase):
    """No template may carry a multi-line ``{# … #}``."""

    def test_no_multiline_hash_comments(self):
        offenders = []
        for path in sorted(TEMPLATE_ROOT.rglob('*.html')):
            body = path.read_text(encoding='utf-8')
            for match in COMMENT.finditer(body):
                if '\n' in match.group(0):
                    line = body[:match.start()].count('\n') + 1
                    offenders.append(f'{path.relative_to(TEMPLATE_ROOT)}:{line}')
        self.assertEqual(
            offenders, [],
            'Multi-line {# #} comments leak their text onto the page. '
            'Use {% comment %}…{% endcomment %} instead. Found at: '
            + ', '.join(offenders)
        )

    def test_multiline_hash_comment_really_does_leak(self):
        """The premise of the test above, pinned so it cannot rot."""
        rendered = Template('{# first\nsecond #}صفحة').render(Context({}))
        self.assertIn('second', rendered)
        self.assertIn(
            'صفحة',
            Template('{% comment %}first\nsecond{% endcomment %}صفحة').render(Context({}))
        )
        self.assertNotIn(
            'second',
            Template('{% comment %}first\nsecond{% endcomment %}صفحة').render(Context({}))
        )


class NumberLocalisationTests(SimpleTestCase):
    """Egyptian separators, not the Maghreb ones Django ships for ``ar``."""

    def test_decimal_point_is_a_dot(self):
        rendered = Template('{{ fee }}').render(Context({'fee': Decimal('50.00')}))
        self.assertEqual(rendered, '50.00')

    def test_zero_balance_is_not_shown_as_a_comma_pair(self):
        rendered = Template('{{ balance }}').render(Context({'balance': Decimal('0.00')}))
        self.assertEqual(rendered, '0.00')

    def test_thousands_are_not_grouped_globally(self):
        """
        Grouping is off at the settings level on purpose: it applies to every
        integer Django renders, which would print payment id 1234 as "1,234".
        """
        rendered = Template('{{ pid }}|{{ year }}').render(
            Context({'pid': 1234, 'year': 2026})
        )
        self.assertEqual(rendered, '1234|2026')

    def test_format_module_is_wired_up(self):
        self.assertIn('config.formats', settings.FORMAT_MODULE_PATH)


class MoneyFilterTests(SimpleTestCase):
    """``money`` / ``egp``: the one way an amount reaches a page."""

    def test_whole_pounds_drop_the_fraction(self):
        self.assertEqual(money(Decimal('50.00')), '50')
        self.assertEqual(egp(Decimal('50.00')), '50 ج.م')

    def test_piastres_are_kept(self):
        self.assertEqual(money(Decimal('1250.50')), '1,250.50')

    def test_thousands_are_grouped(self):
        self.assertEqual(money(Decimal('1000000')), '1,000,000')

    def test_rounds_to_piastres(self):
        self.assertEqual(money(Decimal('1250.567')), '1,250.57')

    def test_unusable_input_reads_as_zero_rather_than_raising(self):
        for value in (None, '', 'abc', [], {}):
            self.assertEqual(money(value), '0')

    def test_currency_never_wraps_away_from_its_amount(self):
        """A narrow phone cell must not put "ج.م" on its own line."""
        self.assertEqual(egp(Decimal('320.00')), '320\u00a0ج.م')

    def test_unusable_input_is_escaped_before_being_marked_safe(self):
        self.assertEqual(egp(None, default='<b>x</b>'),
                         '&lt;b&gt;x&lt;/b&gt;\u00a0ج.م')

    def test_usable_from_a_template(self):
        rendered = Template(
            '{% load money_format %}{{ fee|egp }}'
        ).render(Context({'fee': Decimal('50.00')}))
        self.assertEqual(rendered, '50 ج.م')
