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
import random
from pathlib import Path

from django.conf import settings
from apps.core.constants import (
    RECALL_JP_TO_VI,
    RECALL_MIXED,
    RECALL_VI_TO_JP,
    SHEET_TYPE_RECALL,
)
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

# ipag.ttf (IPAGothic) là bản ĐANG ĐƯỢC KÈM trong assets/fonts/ — giấy phép
# IPA Font License 1.0 cho phép phát hành lại kèm sản phẩm, và chữ kanji/kana
# của nó rộng đều nhau nên rơi vào ô genkoyoshi rất cân. Vẫn dò Noto trước để
# máy nào cài sẵn thì dùng bản quen mắt hơn.
_JP_FONT_FILENAMES = [
    "NotoSansCJK-Regular.ttc",
    "NotoSansJP-Regular.ttf",
    "NotoSansJP-Regular.otf",
    "ipag.ttf",
]
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
CELLS_PER_ROW = 12

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
    """Vẽ chuỗi tiếng Nhật, trả về BỀ RỘNG đã vẽ để chuỗi sau nối tiếp được.

    (x, y) là góc dưới-trái. Chữ Nhật phải đi qua Pillow chứ không vẽ thẳng
    bằng reportlab — xem ghi chú font số 1 ở đầu file.
    """
    if not text:
        return 0
    img = _render_jp_text_image(text, px_size, rgba)
    c.drawImage(ImageReader(img), x, y, width=img.width, height=img.height, mask="auto")
    return img.width


def _jp_text_width(text, px_size):
    if not text:
        return 0
    return _render_jp_text_image(text, px_size, (0, 0, 0, 255)).width


def _fit(text, font_name, size, max_width):
    """Cắt bớt chuỗi Latin cho vừa bề rộng, thêm '…'. Nghĩa tiếng Việt dài quá
    mà không cắt thì tràn ra ngoài lề và đè lên cột bên cạnh."""
    text = text or ""
    if pdfmetrics.stringWidth(text, font_name, size) <= max_width:
        return text
    while text and pdfmetrics.stringWidth(text + "…", font_name, size) > max_width:
        text = text[:-1]
    return text + "…"


# ---------------------------------------------------------------------------
# Khung trang dùng chung
# ---------------------------------------------------------------------------

CONTENT_W = PAGE_W - 2 * MARGIN


BRAND = "毎日BJT"


def _draw_page_frame(c, title, subtitle, page_number):
    """Tiêu đề trang. Phần tên thương hiệu 毎日BJT phải vẽ BẰNG ẢNH.

    DejaVu không có glyph kanji nên `drawString("… 毎日BJT")` in ra hai ô vuông
    tofu — đúng lỗi đã thấy ở bản PDF đầu tiên. Chỉ phần chữ Latin mới đi qua
    reportlab, phần tiếng Nhật đi qua Pillow như mọi chỗ khác trong file này.
    """
    c.setFillColor(INK)
    c.setFont("DejaVu-Bold", 16)
    c.drawString(MARGIN, PAGE_H - 40, title)
    title_w = pdfmetrics.stringWidth(title, "DejaVu-Bold", 16)
    _draw_jp_string(c, MARGIN + title_w + 8, PAGE_H - 42, BRAND, 16)
    c.setStrokeColor(GRID_LINE)
    c.setLineWidth(1)
    c.line(MARGIN, PAGE_H - 48, PAGE_W - MARGIN, PAGE_H - 48)
    c.setFont("DejaVu-Oblique", 9)
    c.drawString(MARGIN, PAGE_H - 62, subtitle)
    c.setFont("DejaVu", 8)
    c.setFillColor(GUIDE)
    c.drawRightString(PAGE_W - MARGIN, 24, str(page_number))
    c.setFillColor(INK)


def _blank_rule(c, x, y, width, label):
    """Một dòng kẻ để viết tay, có nhãn ở đầu dòng."""
    c.setFillColor(INK)
    c.setFont("DejaVu", 9)
    label_w = pdfmetrics.stringWidth(label, "DejaVu", 9)
    c.drawString(x, y + 4, label)
    c.setStrokeColor(GRID_LINE)
    c.setLineWidth(0.7)
    c.line(x + label_w + 6, y, x + width, y)


# ---------------------------------------------------------------------------
# Phiếu 1 — luyện viết ô kẻ (genkoyoshi)
# ---------------------------------------------------------------------------

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


def _guide_chars_for(word, show_guide_character):
    """Chữ mờ để đồ theo, xếp vào các ô ĐẦU của MỖI dòng.

    Bản đầu chỉ đổ chữ mờ vào đúng một ô (dòng đầu, cột đầu) và chỉ lấy
    `word[0]` — với 打ち合わせ thì người học chỉ được đồ mỗi chữ 打, bốn chữ còn
    lại phải tự nhớ mặt chữ. Giờ đổ mờ cả từ, lặp lại ở đầu mỗi dòng để lúc nào
    cũng có mẫu ngay bên trái chỗ đang viết.
    """
    if not show_guide_character:
        return []
    return list(word)[:CELLS_PER_ROW]


def generate_practice_pdf(
    words,
    lines_per_word=2,
    show_guide_character=True,
    show_reading_and_meaning=True,
):
    """Phiếu ô vuông để tập viết tay.

    words: iterable các đối tượng có .word / .reading / .meaning_vi — nhận cả
    Vocabulary lẫn WordItem (từ file người dùng tải lên).
    Trả về (filename, ContentFile) gán thẳng được vào FileField.
    """
    # Tìm + đăng ký font tại đây, không phải lúc import module.
    _ensure_fonts_registered()

    words = list(words)
    lines_per_word = max(1, min(int(lines_per_word or 1), 5))
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    title = "Luyện viết từ vựng tiếng Nhật —"
    subtitle = f"{len(words)} từ đã chọn"
    page_number = 1
    _draw_page_frame(c, title, subtitle, page_number)

    top_y = PAGE_H - 94
    for item in words:
        needed = CELL * lines_per_word + 40
        if top_y - needed < MARGIN + 20:
            c.showPage()
            page_number += 1
            _draw_page_frame(c, title, subtitle, page_number)
            top_y = PAGE_H - 94

        _draw_jp_string(c, MARGIN, top_y - 20, item.word, 16)
        if show_reading_and_meaning:
            _draw_jp_string(c, MARGIN + 120, top_y - 17, item.reading or "", 12)
            c.setFillColor(INK)
            c.setFont("DejaVu", 10)
            c.drawString(
                MARGIN + 260,
                top_y - 16,
                _fit("— " + (item.meaning_vi or ""), "DejaVu", 10, CONTENT_W - 260),
            )

        guides = _guide_chars_for(item.word, show_guide_character)
        grid_top = top_y - 30
        for row in range(lines_per_word):
            y = grid_top - CELL * (row + 1)
            for col in range(CELLS_PER_ROW):
                x = MARGIN + col * CELL
                _draw_cell(c, x, y, CELL, guide_char=guides[col] if col < len(guides) else None)
        top_y = grid_top - CELL * lines_per_word - 18

    c.save()
    buffer.seek(0)
    filename = "phieu_luyen_viet.pdf"
    return filename, ContentFile(buffer.read(), name=filename)


# ---------------------------------------------------------------------------
# Phiếu 2 — ôn lại từ
# ---------------------------------------------------------------------------

PROMPT_LINE_H = 26
RULE_LINE_H = 24
BLOCK_GAP = 12


def _direction_plan(count, direction, rng):
    """Hướng của TỪNG từ, chốt trước khi vẽ.

    Ở chế độ trộn, chia xấp xỉ 50/50 rồi mới xáo vị trí, KHÔNG bốc ngẫu nhiên
    từng từ: bốc từng từ thì 7 từ rất dễ ra 5 JP / 2 VN, phiếu lệch hẳn về một
    phía và mất tác dụng của việc trộn.
    """
    if direction != RECALL_MIXED:
        return [direction or RECALL_JP_TO_VI] * count
    half = count // 2
    plan = [RECALL_JP_TO_VI] * (count - half) + [RECALL_VI_TO_JP] * half
    rng.shuffle(plan)
    return plan


def _draw_recall_block(c, x, y, number, item, direction, include_sentence_box):
    """Vẽ một từ. Trả về chiều cao đã dùng.

    (x, y) là góc TRÊN-trái của khối.
    """
    width = CONTENT_W
    c.setFillColor(INK)
    c.setFont("DejaVu-Bold", 11)
    c.drawString(x, y - 13, f"{number:02d}.")
    prompt_x = x + 26

    if direction == RECALL_VI_TO_JP:
        # Cho sẵn nghĩa tiếng Việt -> người học tự viết từ và cách đọc.
        c.setFont("DejaVu", 12)
        c.drawString(prompt_x, y - 13, _fit(item.meaning_vi or "(chưa có nghĩa)", "DejaVu", 12, width - 26))
        rules = ["Từ:", "Cách đọc:"]
    else:
        # Cho sẵn từ tiếng Nhật -> người học tự viết cách đọc và nghĩa.
        _draw_jp_string(c, prompt_x, y - 18, item.word, 18)
        rules = ["Cách đọc:", "Nghĩa:"]

    used = PROMPT_LINE_H
    for label in rules:
        _blank_rule(c, prompt_x, y - used - 14, width - 26, label)
        used += RULE_LINE_H
    if include_sentence_box:
        _blank_rule(c, prompt_x, y - used - 14, width - 26, "Đặt câu:")
        used += RULE_LINE_H
    return used + BLOCK_GAP


def _draw_answer_key(c, words, title, page_number):
    c.showPage()
    page_number += 1
    _draw_page_frame(c, title, "Đáp án — gấp lại hoặc in riêng trang này", page_number)
    y = PAGE_H - 100
    for index, item in enumerate(words, start=1):
        if y < MARGIN + 20:
            c.showPage()
            page_number += 1
            _draw_page_frame(c, title, "Đáp án (tiếp)", page_number)
            y = PAGE_H - 100
        c.setFillColor(INK)
        c.setFont("DejaVu-Bold", 9)
        c.drawString(MARGIN, y, f"{index:02d}.")
        cursor = MARGIN + 26
        cursor += _draw_jp_string(c, cursor, y - 4, item.word, 13) + 6
        if item.reading:
            cursor += _draw_jp_string(c, cursor, y - 3, item.reading, 10, (120, 112, 96, 255)) + 6
        c.setFillColor(INK)
        c.setFont("DejaVu", 9)
        c.drawString(cursor, y, _fit("— " + (item.meaning_vi or ""), "DejaVu", 9, PAGE_W - MARGIN - cursor))
        y -= 20
    return page_number


def generate_recall_pdf(
    words,
    direction=RECALL_JP_TO_VI,
    include_sentence_box=True,
    include_answer_key=True,
    shuffle_order=False,
    seed=None,
):
    """Phiếu ôn lại từ: cho sẵn một vế, chừa chỗ trống để tự viết vế còn lại.

    `seed` chỉ để test tái lập được thứ tự sau khi xáo trộn; trong ứng dụng cứ
    để None cho mỗi lần in ra một thứ tự khác.
    """
    _ensure_fonts_registered()

    words = list(words)
    rng = random.Random(seed)
    if shuffle_order:
        rng.shuffle(words)
    # Chốt hướng của TỪNG từ trước khi vẽ, để trang đáp án và trang câu hỏi
    # không lệch nhau ở chế độ trộn.
    directions = _direction_plan(len(words), direction, rng)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    title = "Ôn lại từ vựng —"
    subtitle = f"{len(words)} từ · {_direction_label(direction)}"
    page_number = 1
    _draw_page_frame(c, title, subtitle, page_number)

    y = PAGE_H - 94
    block_h = PROMPT_LINE_H + RULE_LINE_H * (3 if include_sentence_box else 2) + BLOCK_GAP
    for index, (item, item_direction) in enumerate(zip(words, directions), start=1):
        if y - block_h < MARGIN + 20:
            c.showPage()
            page_number += 1
            _draw_page_frame(c, title, subtitle, page_number)
            y = PAGE_H - 94
        y -= _draw_recall_block(c, MARGIN, y, index, item, item_direction, include_sentence_box)

    if include_answer_key and words:
        page_number = _draw_answer_key(c, words, title, page_number)

    c.save()
    buffer.seek(0)
    filename = "phieu_on_tap.pdf"
    return filename, ContentFile(buffer.read(), name=filename)


def _direction_label(direction):
    return {
        RECALL_JP_TO_VI: "Nhật → Việt",
        RECALL_VI_TO_JP: "Việt → Nhật",
        RECALL_MIXED: "trộn hai hướng",
    }.get(direction, "Nhật → Việt")


# ---------------------------------------------------------------------------
# Điểm vào dùng chung
# ---------------------------------------------------------------------------

def generate_sheet_pdf(sheet_type, words, **options):
    """Chọn hàm vẽ theo loại phiếu.

    Thêm một loại phiếu mới = thêm một code vào MasterCode code_type "10" VÀ
    thêm một nhánh ở đây. Code lạ (dữ liệu cũ, hoặc ai đó seed thêm mà quên
    viết hàm vẽ) rơi về phiếu luyện viết thay vì ném KeyError giữa lúc người
    dùng đang bấm nút.
    """
    if sheet_type == SHEET_TYPE_RECALL:
        return generate_recall_pdf(
            words,
            direction=options.get("recall_direction") or RECALL_JP_TO_VI,
            include_sentence_box=options.get("include_sentence_box", True),
            include_answer_key=options.get("include_answer_key", True),
            shuffle_order=options.get("shuffle_order", False),
            seed=options.get("seed"),
        )
    return generate_practice_pdf(
        words,
        lines_per_word=options.get("lines_per_word", 2),
        show_guide_character=options.get("show_guide_character", True),
        show_reading_and_meaning=options.get("show_reading_and_meaning", True),
    )
