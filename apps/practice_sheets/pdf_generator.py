"""
Generates a genkoyoshi-style handwriting practice PDF for a list of
Vocabulary objects. Ported from the standalone mockup script
(make_practice_pdf.py) used to produce mau_luyen_viet.pdf.

IMPORTANT font note: the system's Noto Sans CJK .ttc uses CFF (PostScript)
outlines, which reportlab's TTFont parser cannot read directly. Japanese
text is rendered to a transparent PNG with Pillow (freetype handles CFF
fine) and placed as an image on the canvas. Vietnamese text uses DejaVu Sans
(real TrueType/glyf outlines + full Vietnamese diacritic coverage) registered
directly with reportlab.
"""
import io
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

JP_FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
DEJAVU_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAVU_OBLIQUE_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"

pdfmetrics.registerFont(TTFont("DejaVu", DEJAVU_PATH))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", DEJAVU_BOLD_PATH))
pdfmetrics.registerFont(TTFont("DejaVu-Oblique", DEJAVU_OBLIQUE_PATH))

INK = HexColor("#2E2A22")
GUIDE = HexColor("#C9C2AE")
GRID_LINE = HexColor("#DCD3C0")

PAGE_W, PAGE_H = A4
MARGIN = 40
CELL = 40
CELLS_PER_ROW = 10

_jp_font_cache = {}


def _jp_font(px_size):
    if px_size not in _jp_font_cache:
        _jp_font_cache[px_size] = ImageFont.truetype(JP_FONT_PATH, px_size, index=0)
    return _jp_font_cache[px_size]


def _render_jp_text_image(text, px_size, rgba):
    font = _jp_font(px_size)
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font)
    w = max(1, bbox[2] - bbox[0])
    h = max(1, bbox[3] - bbox[1])
    pad = 4
    img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=rgba)
    return img


def _draw_jp_string(c, x, y, text, px_size, rgba=(46, 42, 34, 255)):
    img = _render_jp_text_image(text, px_size, rgba)
    c.drawImage(ImageReader(img), x, y, width=img.width, height=img.height, mask="auto")


def _draw_cell(c, x, y, size, guide_char=None):
    c.setStrokeColor(GRID_LINE)
    c.setLineWidth(0.6)
    c.rect(x, y, size, size)
    c.saveState()
    c.setDash(1, 2)
    c.line(x + size / 2, y, x + size / 2, y + size)
    c.line(x, y + size / 2, x + size, y + size / 2)
    c.restoreState()
    if guide_char:
        px = int(size * 0.78)
        img = _render_jp_text_image(guide_char, px, (201, 194, 174, 255))
        cx = x + size / 2 - img.width / 2
        cy = y + size / 2 - img.height / 2
        c.drawImage(ImageReader(img), cx, cy, width=img.width, height=img.height, mask="auto")


def _draw_page_header(c, subtitle):
    c.setFillColor(INK)
    c.setFont("DejaVu-Bold", 16)
    c.drawString(MARGIN, PAGE_H - 40, "Luyện viết từ vựng tiếng Nhật — BJT GOI")
    c.setStrokeColor(GRID_LINE)
    c.setLineWidth(1)
    c.line(MARGIN, PAGE_H - 48, PAGE_W - MARGIN, PAGE_H - 48)
    c.setFont("DejaVu-Oblique", 9)
    c.drawString(MARGIN, PAGE_H - 62, subtitle)


def generate_practice_pdf(words, lines_per_word=2, show_guide_character=True, show_reading_and_meaning=True):
    """
    words: iterable of Vocabulary model instances (word, reading, meaning_vi)
    Returns: (filename: str, ContentFile) ready to assign to a FileField
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    subtitle = f"{len(words)} từ đã chọn"
    _draw_page_header(c, subtitle)

    top_y = PAGE_H - 94
    for item in words:
        needed = CELL * lines_per_word + 40
        if top_y - needed < MARGIN:
            c.showPage()
            _draw_page_header(c, subtitle)
            top_y = PAGE_H - 74

        _draw_jp_string(c, MARGIN, top_y - 20, item.word, 16)
        if show_reading_and_meaning:
            _draw_jp_string(c, MARGIN + 100, top_y - 17, item.reading, 12)
            c.setFillColor(INK)
            c.setFont("DejaVu", 10)
            c.drawString(MARGIN + 250, top_y - 16, "- " + item.meaning_vi)

        grid_top = top_y - 30
        for row in range(lines_per_word):
            y = grid_top - CELL * (row + 1)
            for col in range(CELLS_PER_ROW):
                x = MARGIN + col * CELL
                guide = item.word[0] if (row == 0 and col == 0 and show_guide_character) else None
                _draw_cell(c, x, y, CELL, guide_char=guide)
        top_y = grid_top - CELL * lines_per_word - 18

    c.save()
    buffer.seek(0)
    filename = "phieu_luyen_viet.pdf"
    return filename, ContentFile(buffer.read(), name=filename)
