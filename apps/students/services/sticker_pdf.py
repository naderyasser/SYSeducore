from io import BytesIO

from reportlab.lib.pagesizes import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import barcode
from barcode.writer import ImageWriter
from PIL import Image

from apps.core.pdf import get_arabic_fonts, rtl


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
    ar_font, ar_bold = get_arabic_fonts()

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
    c.setFont(ar_bold, 7)
    c.drawString(22 * mm, 5.5 * mm, str(student.student_code))

    # Student name (right bottom, truncated + RTL-reshaped)
    name = (student.full_name or '')[:10]
    if len(student.full_name or '') > 10:
        name += '…'
    name = rtl(name)
    c.setFont(ar_font, 5)
    c.drawString(22 * mm, 2 * mm, name)

    c.showPage()
    c.save()
    return buf.getvalue()
