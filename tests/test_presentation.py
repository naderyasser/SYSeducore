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
from django.test import SimpleTestCase, TestCase

from apps.core.templatetags.money_format import egp, money

TEMPLATE_ROOT = Path(settings.BASE_DIR) / 'templates'

# ``{#`` … first ``#}``. A match containing a newline is a comment the
# template engine will not treat as one.
COMMENT = re.compile(r'\{#.*?#\}', re.S)

# The same trap for real tags. Django's tokeniser pattern is
# ``({%.*?%}|{{.*?}}|{#.*?#})`` with no DOTALL flag, so a tag wrapped across
# two lines is not a tag — it is printed.
TAG = re.compile(r'\{%.*?%\}|\{\{.*?\}\}', re.S)


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

    def test_no_multiline_tags(self):
        """
        A ``{% if %}``/``{{ }}`` may not wrap across lines either. The session
        detail screen had ``{% elif`` at the end of a line three times, so
        every present student's row read
        "حاضر {% elif attendance.status == 'late' %}متأخر …".
        """
        offenders = []
        for path in sorted(TEMPLATE_ROOT.rglob('*.html')):
            body = path.read_text(encoding='utf-8')
            for match in TAG.finditer(body):
                if '\n' in match.group(0):
                    line = body[:match.start()].count('\n') + 1
                    offenders.append(
                        f'{path.relative_to(TEMPLATE_ROOT)}:{line}'
                    )
        self.assertEqual(
            offenders, [],
            'A Django template tag cannot span lines — it is rendered as '
            'text instead. Found at: ' + ', '.join(offenders)
        )

    def test_multiline_tag_really_does_leak(self):
        """The premise of the test above, pinned so it cannot rot."""
        rendered = Template(
            "{% if 1 %}نعم {% elif\n 0 %}لا{% endif %}"
        ).render(Context({}))
        self.assertIn('elif', rendered)

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


class ErrorPageTests(SimpleTestCase):
    """
    A refused page has to be as Arabic as every other page.

    403 had no handler, so Django's built-in page answered: "403 Forbidden",
    in English, unstyled, with no link back. A teacher who opened a screen
    above their role saw that, and the Arabic sentence the permission check
    actually raises was discarded with it.
    """

    def _page(self, handler, exception=None):
        from django.test import RequestFactory
        request = RequestFactory().get('/payments/')
        response = handler(request, exception) if exception is not None else handler(request)
        return response, response.content.decode('utf-8')

    def test_403_is_arabic_and_right_to_left(self):
        from config.urls import error_403
        response, body = self._page(error_403, exception=None)
        self.assertEqual(response.status_code, 403)
        self.assertIn('dir="rtl"', body)
        self.assertIn('لا تملك صلاحية الدخول', body)
        self.assertNotIn('Forbidden', body)

    def test_403_repeats_the_message_the_permission_check_raised(self):
        from django.core.exceptions import PermissionDenied
        from config.urls import error_403
        _, body = self._page(
            error_403, exception=PermissionDenied('ليس لديك صلاحية للقيام بهذا الإجراء')
        )
        self.assertIn('ليس لديك صلاحية للقيام بهذا الإجراء', body)

    def test_403_offers_a_way_back(self):
        from config.urls import error_403
        _, body = self._page(error_403, exception=None)
        self.assertIn('href="/"', body)

    def test_handler_is_registered(self):
        from config import urls
        self.assertEqual(urls.handler403, 'config.urls.error_403')


class CurrencyMarkupTests(SimpleTestCase):
    """No screen assembles an amount by hand any more."""

    # ``{{ value }} ج.م`` — the pattern that kept the trailing ``.00`` and
    # skipped thousand grouping. ``|egp`` renders both parts together.
    AD_HOC = re.compile(r'\{\{[^}]*\}\}\s*ج\.م')

    def test_no_template_appends_the_currency_by_hand(self):
        offenders = []
        for path in sorted(TEMPLATE_ROOT.rglob('*.html')):
            for number, line in enumerate(
                path.read_text(encoding='utf-8').split('\n'), start=1
            ):
                if '${' in line:  # a JS template literal, not a Django variable
                    continue
                if self.AD_HOC.search(line):
                    offenders.append(f'{path.relative_to(TEMPLATE_ROOT)}:{number}')
        self.assertEqual(
            offenders, [],
            'Render money with |egp rather than "{{ value }} ج.م": the filter '
            'drops a zero fraction and groups thousands. Found at: '
            + ', '.join(offenders)
        )


class LoginRedirectTests(TestCase):
    """
    Signing in with a ``next`` must land on that page, not on a 500.

    ``url_has_allowed_host_and_scheme`` takes ``require_https``; the call
    passed ``require_secure``, which Django rejects with a ``TypeError``. The
    crash happened *after* ``login()``, so the session existed and the person
    was shown a server error instead of the page they had clicked. Anyone
    whose session expired hit it: the redirect to the login screen always
    carries a ``next``.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(
            username='desk', password='pw12345!', role='supervisor'
        )

    def test_login_with_next_lands_on_that_page(self):
        response = self.client.post(
            '/accounts/login/',
            {'username': 'desk', 'password': 'pw12345!', 'next': '/students/'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/students/')

    def test_login_without_next_lands_on_the_dashboard(self):
        response = self.client.post(
            '/accounts/login/', {'username': 'desk', 'password': 'pw12345!'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/reports/', response['Location'])

    def test_a_next_pointing_off_site_is_ignored(self):
        response = self.client.post(
            '/accounts/login/',
            {'username': 'desk', 'password': 'pw12345!',
             'next': 'https://example.com/steal'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('example.com', response['Location'])
