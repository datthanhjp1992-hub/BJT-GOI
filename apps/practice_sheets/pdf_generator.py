"""
Sinh PDF luyện viết kiểu ô vuông (genkoyoshi) cho một danh sách Vocabulary.
Port từ script mockup make_practice_pdf.py (tạo ra mau_luyen_viet.pdf).

GHI CHÚ VỀ FONT — đọc trước khi sửa
-----------------------------------
1. Tiếng Nhật: Noto Sans CJK trên hệ thống là .ttc dùng outline CFF
   (PostScript); parser TTFont của reportlab KHÔNG đọc được. Nên chữ Nhật để
   Pillow (freetype, đọc CFF tốt) vẽ ra PNG trong suốt rồi chèn lên canvas.
2. Tiếng Việt: DejaVu Sans — TrueType/glyf thật, phủ đủ dấu tiếng Việt — đăng
   ký thẳng với reportlab.
3. TÌM FONT LÚC CHẠY, KHÔNG PHẢI LÚC IMPORT. Bản đầu hardcode đường dẫn
   /usr/share/fonts/... rồi gọi registerFont ngay ở cấp module. Máy nào không
   có sẵn font (Windows, và ảnh chạy của Render) thì import module này là nổ —
   mà config/urls.py có include app này, nên TOÀN BỘ site chết, kể cả
   `manage.py check` và `collectstatic`. Đúng lỗi đã làm build Render đỏ ngày
   13/09. Giờ font chỉ được tìm khi thực sự sinh PDF; thiếu font thì chỉ SC10
   báo lỗi rõ ràng, phần còn lại của web vẫn chạy bình thường.

Chỉ định font thủ công (tuỳ chọn):
    PRACTICE_SHEET_FONT_DIR   thư mục chứa DejaVuSans*.ttf
    PRACTICE_SHEET_JP_FONT    đường dẫn đầy đủ tới 1 font CJK
Hoặc thả file .ttf/.ttc vào  <BASE_DIR>/assets/fonts/  — chỗ đó được dò sẵn.
"""
import io
import os
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


class PracticeSheetFontError(RuntimeError):
    """Máy đang chạy không có font cần thiết để sinh PDF luyện viết."""


# Tên logic -> (tên file tìm trong thư mục font, các đường dẫn hệ thống).
# Thứ tự: Debian/Ubuntu, Fedora, Arch, macOS, rồi Windows. Windows không có
# DejaVu nên rơi về Arial/Segoe UI — hai font này cũng phủ đủ dấu tiếng Việt.
_VI_FONTS = {
    "DejaVu": ("DejaVuSans.ttf", [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/Library/Fonts/DejaVuSans.ttf",
        "C:/Windows/Fonts/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]),
    "DejaVu-Bold": ("DejaVuSans-Bold.ttf", [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/Library/Fonts/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ]),
    "DejaVu-Oblique": ("DejaVuSans-Oblique.ttf", [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Oblique.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Oblique.ttf",
        "/Library/Fonts/DejaVuSans-Oblique.ttf",
        "C:/Windows/Fonts/DejaVuSans-Oblique.ttf",
        "C:/Windows/Fonts/ariali.ttf",
        "C:/Windows/Fonts/segoeuii.ttf",
    ]),
}

_JP_FONT_FILENAMES = ["NotoSansCJK-Regular.ttc", "NotoSansJP-Regular.ttf", "NotoSansJP-Regular.otf"]
_JP_FONT_SYSTEM_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]

INK = HexColor("#2E2A22")
GUIDE = HexColor("#C9C2AE")
GRID_LINE = HexColor("#DCD3C0")

PAGE_W, PAGE_H = A4
MARGIN = 40
CELL = 40
CELLS_PER_ROW = 10

_jp_font_cache = {}
_jp_font_path_cache = None
_fonts_registered = False


def _search_dirs():
    """Thư mục font ưu tiên hơn đường dẫn hệ thống: biến môi trường trước, rồi
    thư mục kèm repo (dùng khi máy chủ không cài sẵn font, vd Render)."""
    dirs = []
    env_dir = os.environ.get("PRACTICE_SHEET_FONT_DIR")
    if env_dir:
        dirs.append(Path(env_dir))
    dirs.append(Path(settings.BASE_DIR) / "assets" / "fonts")
    return dirs


def _first_existing(paths):
    for path in paths:
        if path and os.path.isfile(path):
            return str(path)
    return None


def _resolve_font(basename, system_paths):
    found = _first_existing([d / basename for d in _search_dirs()])
    return found or _first_existing(system_paths)


def _missing_font_error(what, hints):
    return PracticeSheetFontError(
        f"Không tìm thấy font {what} để sinh PDF luyện viết. "
        f"Đã dò: {', '.join(hints)}. "
        "Cách xử lý: cài font trên máy chủ, hoặc chép file font vào "
        "<BASE_DIR>/assets/fonts/, hoặc trỏ biến môi trường "
        "PRACTICE_SHEET_FONT_DIR / PRACTICE_SHEET_JP_FONT tới nơi chứa font."
    )


def _ensure_fonts_registered():
    """Đăng ký font tiếng Việt với reportlab. Gọi ở đầu generate_practice_pdf,
    KHÔNG gọi ở cấp module — xem ghi chú số 3 đầu file."""
    global _fonts_registered
    if _fonts_registered:
        return

    registered = set(pdfmetrics.getRegisteredFontNames())
    missing = []
    for logical_name, (basename, system_paths) in _VI_FONTS.items():
        if logical_name in registered:
            continue
        path = _resolve_font(basename, system_paths)
        if path is None:
            missing.append(basename)
            continue
        pdfmetrics.registerFont(TTFont(logical_name, path))

    if missing:
        raise _missing_font_error("tiếng Việt (" + ", ".join(missing) + ")", ["assets/fonts/"] + [
            p for _, (_, paths) in _VI_FONTS.items() for p in paths[:1]
        ])
    _fonts_registered = True


def _jp_font(px_size):
    global _jp_font_path_cache
    if _jp_font_path_cache is None:
        path = os.environ.get("PRACTICE_SHEET_JP_FONT")
        if not path or not os.path.isfile(path):
            path = _first_existing(
                [d / name for d in _search_dirs() for name in _JP_FONT_FILENAMES]
            ) or _first_existing(_JP_FONT_SYSTEM_PATHS)
        if path is None:
            raise _missing_font_error("tiếng Nhật (Noto Sans CJK)", _JP_FONT_SYSTEM_PATHS[:2])
        _jp_font_path_cache = path

    if px_size not in _jp_font_cache:
        _jp_font_cache[px_size] = ImageFont.truetype(_jp_font_path_cache, px_size, index=0)
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
    # Tìm + đăng ký font tại đây, không phải lúc import module.
    _ensure_fonts_registered()

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
