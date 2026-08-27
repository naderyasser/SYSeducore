"""
Shared PDF/Arabic bootstrap for reportlab-based generators.

Two things every reportlab call site needs and used to duplicate/get wrong
in ``apps.students.services.sticker_pdf``:

1. An Arabic-capable font actually registered with reportlab. ``Cairo``
   cannot be used here: ``static/fonts/`` never shipped
   ``Cairo-Regular.ttf``/``Cairo-Bold.ttf`` (only the browser-only
   ``Cairo-Variable.ttf``), and empirically that variable font's cmap is
   missing several isolated Arabic presentation-form codepoints that
   ``arabic_reshaper`` emits (e.g. isolated alef U+FE8D) — real names like
   "محمد أحمد" render with missing glyphs. ``DejaVuSans.ttf`` covers every
   codepoint ``arabic_reshaper`` produces and is what the old code actually
   fell back to anyway, so it is used explicitly instead of being a silent
   fallback of a doomed first attempt.
2. The reshape+bidi call every Arabic string going through
   ``canvas.drawString`` needs (reportlab draws left-to-right; Arabic text
   must be pre-shaped and reordered).
"""
import logging
import os

from django.conf import settings
from django.contrib.staticfiles.finders import find as find_static
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_BIDI = True
except ImportError:
    _HAS_BIDI = False

_FONT_NAME = 'DejaVuSans'
_FONT_BOLD_NAME = 'DejaVuSans-Bold'
_registered = False
_fallback_to_helvetica = False


def _resolve_font_path(filename):
    """Prefer the staticfiles finder (works under collectstatic too); fall
    back to the raw ``static/fonts`` path for contexts where the finder
    isn't wired up (e.g. a bare script)."""
    found = find_static(f'fonts/{filename}')
    if found:
        return found
    return os.path.join(settings.BASE_DIR, 'static', 'fonts', filename)


def get_arabic_fonts():
    """
    Returns ``(regular_font_name, bold_font_name)``, registering them with
    reportlab on first call. Falls back to ``('Helvetica', 'Helvetica-Bold')``
    — which cannot render Arabic — only if DejaVuSans genuinely isn't on
    disk; that failure is logged, not swallowed, so it doesn't go unnoticed
    for months the way the old bug did.
    """
    global _registered, _fallback_to_helvetica

    if _registered:
        if _fallback_to_helvetica:
            return 'Helvetica', 'Helvetica-Bold'
        return _FONT_NAME, _FONT_BOLD_NAME

    reg_path = _resolve_font_path('DejaVuSans.ttf')
    bold_path = _resolve_font_path('DejaVuSans-Bold.ttf')

    try:
        pdfmetrics.registerFont(TTFont(_FONT_NAME, reg_path))
        if os.path.isfile(bold_path):
            pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, bold_path))
        else:
            # Missing bold file must not sink the (working) regular
            # registration — alias bold to regular instead.
            pdfmetrics.registerFont(TTFont(_FONT_BOLD_NAME, reg_path))
        _registered = True
        return _FONT_NAME, _FONT_BOLD_NAME
    except Exception:
        logger.exception('Failed to register DejaVuSans for PDF Arabic text — falling back to Helvetica (no Arabic support)')
        _registered = True
        _fallback_to_helvetica = True
        return 'Helvetica', 'Helvetica-Bold'


def rtl(text):
    """Reshape + bidi-reorder Arabic text for reportlab's LTR drawString."""
    if not text or not _HAS_BIDI:
        return text or ''
    return get_display(arabic_reshaper.reshape(text))
