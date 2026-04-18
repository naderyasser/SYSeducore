from io import BytesIO
import os

from reportlab.lib.pagesizes import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import barcode
from barcode.writer import ImageWriter
from PIL import Image
from django.conf import settings

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_BIDI = True
except ImportError:
    _HAS_BIDI = False


FONTS_DIR = os.path.join(settings.BASE_DIR, 'static', 'fonts')

# Register fonts — try Cairo first, fall back to DejaVuSans (Arabic-capable)
_font_registered = False
AR_FONT = 'Helvetica'
AR_BOLD = 'Helvetica-Bold'

def _ensure_fonts():
    global _font_registered, AR_FONT, AR_BOLD
    if _font_registered:
        return
    _font_registered = True
    for name, regular, bold in [
        ('Cairo', 'Cairo-Regular.ttf', 'Cairo-Bold.ttf'),
        ('DejaVuSans', 'DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'),
    ]:
        reg_path = os.path.join(FONTS_DIR, regular)
        bold_path = os.path.join(FONTS_DIR, bold)
        if os.path.isfile(reg_path) and os.path.getsize(reg_path) > 1000:
            try:
                pdfmetrics.registerFont(TTFont(name, reg_path))
                pdfmetrics.registerFont(TTFont(f'{name}-Bold', bold_path))
                AR_FONT = name
                AR_BOLD = f'{name}-Bold'
                return
            except Exception:
                continue


def _generate_barcode_png(code: str) -> BytesIO:
    buf = BytesIO()
    code128 = barcode.get('code128', str(code), writer=ImageWriter())
    code128.write(buf, options={
        'module_width': 0.25,
        'module_height': 8.0,
        'quiet_zone': 1.0,
        'write_text': False,
        'dpi': 300,
    })
    buf.seek(0)
    return buf


def build_sticker_pdf(student) -> bytes:
    """Generate a 35mm x 10mm thermal sticker PDF."""
    _ensure_fonts()

    buf = BytesIO()
    page_w, page_h = 35 * mm, 10 * mm
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setTitle(f"Sticker-{student.student_code}")

    # Barcode: left side, ~20mm wide x 7mm tall
    bc_buf = _generate_barcode_png(student.student_code)
    bc_img = ImageReader(Image.open(bc_buf))
    c.drawImage(bc_img, 0.5 * mm, 1.5 * mm,
                width=20 * mm, height=7 * mm,
                preserveAspectRatio=True, mask='auto')

    # Student code (right top)
    c.setFont(AR_BOLD, 7)
    c.drawString(22 * mm, 5.5 * mm, str(student.student_code))

    # Student name (right bottom, truncated + RTL-reshaped)
    name = (student.full_name or '')[:10]
    if len(student.full_name or '') > 10:
        name += '…'
    if _HAS_BIDI and name:
        name = get_display(arabic_reshaper.reshape(name))
    c.setFont(AR_FONT, 5)
    c.drawString(22 * mm, 2 * mm, name)

    c.showPage()
    c.save()
    return buf.getvalue()
