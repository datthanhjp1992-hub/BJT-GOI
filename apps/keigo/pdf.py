"""
SC17 -- PDF on tap MOT chuong kinh ngu (nut "In on tap chuong nay").

In TOAN BO noi dung cua chuong, dung thu tu danh sach muc tren trang bai hoc
(selectors.lesson_items): bang dac biet -> tung mau ngu phap + vi du -> bang
cap tu. Khong co tuy chon -- dang o chuong nao thi in chuong do.

GHI CHU VE FONT -- khac voi apps/practice_sheets/pdf_generator.py
-----------------------------------------------------------------
pdf_generator ve chu Nhat thanh ANH qua Pillow vi no do Noto CJK truoc (outline
CFF, reportlab khong doc duoc). O day chi dung assets/fonts/ipag.ttf -- IPAGothic
la TrueType glyf that nen reportlab dang ky THANG duoc: chu trong PDF la chu
that (chon/copy/tim duoc, file nhe), va Paragraph tu xuong dong cau dai. Vi vay
KHONG do Noto o day. ipag.ttf va DejaVuSans*.ttf da kem san trong repo (xem
claude/sc10-phieu-pdf.md) nen Render chay duoc khong can apt install.

IPAGothic khong co du dau tieng Viet, DejaVu khong co kanji -> moi chuoi duoc
cat thanh tung doan theo ky tu (_runs) va boc <font name=...> cho dung font.

Tim font LUC SINH PDF, khong phai luc import -- thieu font chi lam nut nay bao
loi, khong lam chet ca site (bai hoc 13/09 cua SC10).
"""
import io
import os
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.constants import keigo_style_choices
from apps.core.properties import label

from . import selectors
from .templatetags.keigo_tags import RUBY_RE


class KeigoPdfFontError(RuntimeError):
    """May dang chay khong co font can thiet de sinh PDF on tap."""


FONT_JP = "KeigoIPAGothic"
FONT_VI = "KeigoDejaVu"
FONT_VI_BOLD = "KeigoDejaVuBold"
_FONT_FILES = {FONT_JP: "ipag.ttf", FONT_VI: "DejaVuSans.ttf", FONT_VI_BOLD: "DejaVuSans-Bold.ttf"}

INK = HexColor("#24211D")
SOFT = HexColor("#6b6455")
ACCENT = HexColor("#B5432E")
RULE = HexColor("#DCD3C0")
PANEL = HexColor("#FAF6EE")
WRONG_BG = HexColor("#F7ECE8")
OK_BG = HexColor("#EAF1EF")
MARGIN = 16 * mm


def _font_dirs():
    dirs = [Path(settings.BASE_DIR) / "assets" / "fonts"]
    extra = os.environ.get("PRACTICE_SHEET_FONT_DIR")  # dung chung bien voi SC10
    if extra:
        dirs.insert(0, Path(extra))
    return dirs


def _ensure_fonts():
    registered = set(pdfmetrics.getRegisteredFontNames())
    for name, filename in _FONT_FILES.items():
        if name in registered:
            continue
        path = next((d / filename for d in _font_dirs() if (d / filename).is_file()), None)
        if path is None:
            raise KeigoPdfFontError(f"Khong tim thay {filename} trong {', '.join(map(str, _font_dirs()))}")
        pdfmetrics.registerFont(TTFont(name, str(path)))


# --- Chuoi -> markup cua Paragraph -------------------------------------------

def _is_jp(ch):
    # Tu U+2E80 tro len: CJK, kana, dau cau 「」・～／ toan goc (FF00-FFEF).
    # Moi thu duoi do (Latin + dau tieng Viet, → ★ × ○) de DejaVu.
    return ord(ch) >= 0x2E80


def _runs(text, bold=False):
    """Cat chuoi thanh doan cung font, escape tung doan."""
    if not text:
        return ""
    vi_font = FONT_VI_BOLD if bold else FONT_VI
    out, buf, cur = [], [], None
    for ch in str(text):
        font = FONT_JP if _is_jp(ch) else vi_font
        if font != cur and buf:
            out.append(f'<font name="{cur}">{escape("".join(buf))}</font>')
            buf = []
        cur = font
        buf.append(ch)
    if buf:
        out.append(f'<font name="{cur}">{escape("".join(buf))}</font>')
    return "".join(out)


def _mk(text, bold=False):
    """Nhu _runs nhung doi ruby {漢字|かんじ} thanh 漢字(かんじ), phan doc mau nhat."""
    text = str(text or "")
    out, pos = [], 0
    for m in RUBY_RE.finditer(text):
        out.append(_runs(text[pos:m.start()], bold))
        out.append(_runs(m.group(1), bold))
        out.append(f'<font color="#8a8272">{_runs("(" + m.group(2) + ")")}</font>')
        pos = m.end()
    out.append(_runs(text[pos:], bold))
    return "".join(out)


# --- Style --------------------------------------------------------------------

def _styles():
    base = dict(fontName=FONT_VI, textColor=INK)
    return {
        "brand": ParagraphStyle("brand", fontName=FONT_VI, fontSize=8.5, leading=11, textColor=SOFT),
        "title": ParagraphStyle("title", fontSize=22, leading=28, spaceAfter=2, **base),
        "meta": ParagraphStyle("meta", fontSize=9.5, leading=13, textColor=SOFT, fontName=FONT_VI),
        "summary": ParagraphStyle("summary", fontSize=10, leading=15, spaceBefore=6, **base),
        "kicker": ParagraphStyle("kicker", fontSize=8.5, leading=11, textColor=ACCENT, fontName=FONT_VI, spaceBefore=14),
        "h2": ParagraphStyle("h2", fontSize=15, leading=21, spaceAfter=5, **base),
        "sub": ParagraphStyle("sub", fontSize=10, leading=14, spaceBefore=8, spaceAfter=3, **base),
        "formula": ParagraphStyle("formula", fontSize=10, leading=14, textColor=ACCENT, fontName=FONT_VI),
        "note": ParagraphStyle("note", fontSize=8.5, leading=12, textColor=SOFT, fontName=FONT_VI, spaceAfter=3),
        "ex": ParagraphStyle("ex", fontSize=11, leading=17, leftIndent=12, firstLineIndent=-12, spaceAfter=2, **base),
        "cell": ParagraphStyle("cell", fontSize=10.5, leading=15, **base),
        "cell_acc": ParagraphStyle("cell_acc", fontSize=10.5, leading=15, textColor=ACCENT, fontName=FONT_VI),
        "cell_soft": ParagraphStyle("cell_soft", fontSize=8, leading=10, textColor=SOFT, fontName=FONT_VI),
    }


def _grid(rows, widths, extra=()):
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        *extra,
    ]))
    return t


# --- Tung loai muc ------------------------------------------------------------

def _irregular_flowables(item, st, width):
    names = dict(keigo_style_choices())
    out = []
    for group in item.detail["groups"]:
        if item.detail["show_group_heading"]:
            out.append(Paragraph(_mk(names.get(group["style_code"], group["style_code"]), bold=True), st["sub"]))
        rows = []
        for row in group["verbs"]:
            left = [Paragraph(_mk(row["verb"].plain_form), st["cell"])]
            if row["verb"].meaning_vi:
                left.append(Paragraph(_mk(row["verb"].meaning_vi), st["cell_soft"]))
            forms = _runs("、").join(
                _mk(f.form) + (f' <font size="8" color="#6b6455">{_mk(f.note_vi)}</font>' if f.note_vi else "")
                for f in row["forms"])
            rows.append([left, Paragraph("→", st["cell"]), Paragraph(forms, st["cell_acc"])])
        out.append(_grid(rows, [34 * mm, 7 * mm, width - 41 * mm]))
    return out


def _pattern_flowables(item, st, width):
    p = item.pattern
    out = []
    if p.formation:
        out.append(Paragraph(f'{_runs(label("keigo.lesson.formula"))}:  {_mk(p.formation)}', st["formula"]))
        out.append(Spacer(1, 4))
    if p.explanation_vi:
        out.append(Paragraph(_mk(p.explanation_vi), st["note"]))
    for block in item.detail["blocks"]:
        if block["kind"] == "dialog":
            rows = []
            for e in block["lines"]:
                text = _mk("「" + e.sentence_jp + "」")
                if e.sentence_vi:
                    text += f'<br/><font size="9" color="#6b6455">{_mk(e.sentence_vi)}</font>'
                rows.append([Paragraph(_mk(e.speaker, bold=True), st["cell"]), Paragraph(text, st["cell"])])
            t = Table(rows, colWidths=[10 * mm, width - 14 * mm], hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                ("LINEBEFORE", (0, 0), (0, -1), 2, HexColor("#3F6B63")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            out += [Spacer(1, 2), t, Spacer(1, 4)]
        else:
            e = block["example"]
            mark = "×" if not e.is_correct else "・"
            text = f'<font color="#B5432E">{_runs(mark)}</font>{_mk(e.sentence_jp)}'
            if e.sentence_vi:
                text += f'<br/><font size="9" color="#6b6455">{_mk(e.sentence_vi)}</font>'
            out.append(Paragraph(text, st["ex"]))
    if not item.detail["blocks"]:
        out.append(Paragraph(_runs(label("keigo.lesson.examples_empty")), st["note"]))
    return out


def _pairs_flowables(item, st, width):
    out = []
    wrong = item.detail["is_wrong_type"]
    for group in item.detail["groups"]:
        if group["label"]:
            out.append(Paragraph(_mk(group["label"], bold=True), st["sub"]))
        rows, extra = [], []
        for p in group["pairs"]:
            note = f'<br/><font size="8" color="#6b6455">{_mk(p.note_vi)}</font>' if p.note_vi else ""
            if wrong:
                r = len(rows)
                if p.casual:
                    rows.append([Paragraph('<font color="#B5432E">×</font>', st["cell"]),
                                 Paragraph(f'<strike>{_mk(p.casual)}</strike>', st["cell"])])
                    extra.append(("BACKGROUND", (0, r), (-1, r), WRONG_BG))
                    r += 1
                rows.append([Paragraph('<font color="#3F6B63">○</font>', st["cell"]),
                             Paragraph(_mk(p.polite) + note, st["cell"])])
                extra.append(("BACKGROUND", (0, r), (-1, r), OK_BG))
            elif p.casual:
                rows.append([Paragraph(_mk(p.casual), st["cell"]), Paragraph("→", st["cell"]),
                             Paragraph(_mk(p.polite) + note, st["cell_acc"])])
            else:
                rows.append([Paragraph(_runs("・"), st["cell"]), "",
                             Paragraph(_mk(p.polite) + note, st["cell_acc"])])
        if wrong:
            out.append(_grid(rows, [8 * mm, width - 8 * mm], extra))
        else:
            half = (width - 7 * mm) / 2
            if all(not p.casual for p in group["pairs"]):  # tu dem: chi co ve phai
                out.append(_grid(rows, [6 * mm, 0.1, width - 6 * mm - 0.1]))
            else:
                out.append(_grid(rows, [half, 7 * mm, half]))
        out.append(Spacer(1, 4))
    return out


# --- Ghep trang ---------------------------------------------------------------

def lesson_pdf_filename(lesson, lesson_number):
    return f"kinh-ngu-chuong-{lesson_number}-{lesson.slug}.pdf"


def build_lesson_pdf(lesson, lesson_number, lesson_total):
    """Tra bytes PDF on tap cua mot chuong. Nem KeigoPdfFontError neu thieu font."""
    _ensure_fonts()
    st = _styles()
    width = A4[0] - 2 * MARGIN
    title = lesson.title.lower().capitalize()
    chapter = f'{label("keigo.lesson.chapter")} {lesson_number} / {lesson_total}'

    items = selectors.lesson_items(lesson)
    stats = selectors.lesson_stats(lesson)
    pattern_total = sum(1 for i in items if i.kind == selectors.KIND_PATTERN)

    story = [
        Paragraph(_runs(f'毎日BJT · {label("common.nav.keigo")} · {chapter}'), st["brand"]),
        Paragraph(_runs(title), st["title"]),
    ]
    meta = [f"{n} {label(k)}" for n, k in (
        (stats["pattern_count"], "keigo.index.stat.pattern"),
        (stats["example_count"], "keigo.lesson.stat.example"),
        (stats["irregular_count"], "keigo.lesson.stat.irregular"),
        (stats["pair_count"], "keigo.lesson.stat.pair"),
    ) if n]
    if meta:
        story.append(Paragraph(_runs(" · ".join(meta)), st["meta"]))
    if lesson.summary_vi:
        story.append(Paragraph(_mk(lesson.summary_vi), st["summary"]))
    story.append(Spacer(1, 6))

    for item in items:
        selectors.load_item_detail(lesson, item)
        if item.kind == selectors.KIND_PATTERN:
            kicker = f'{label("keigo.lesson.kicker.pattern")} {item.badge} / {pattern_total}'
            heading, body = item.title, _pattern_flowables(item, st, width)
        elif item.kind == selectors.KIND_IRREGULAR:
            kicker = f'★ {label("keigo.lesson.irregular.title")}'
            heading, body = label("keigo.lesson.irregular.heading"), _irregular_flowables(item, st, width)
        else:
            kicker = f'※ {label("keigo.lesson.kicker.pairs")}'
            heading, body = item.title, _pairs_flowables(item, st, width)
        head = [Paragraph(_runs(kicker), st["kicker"]), Paragraph(_mk(heading), st["h2"])]
        # Giu tieu de muc dinh voi dong noi dung dau tien, khong de tieu de mo coi cuoi trang.
        story.append(KeepTogether(head + body[:1]))
        story.extend(body[1:])

    footer_text = f"毎日BJT — {label('common.nav.keigo')} · {chapter}: {title}"

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.line(MARGIN, 11 * mm, A4[0] - MARGIN, 11 * mm)
        x = MARGIN
        for chunk_font, chunk in _split_plain(footer_text):
            canvas.setFont(chunk_font, 7.5)
            canvas.setFillColor(SOFT)
            canvas.drawString(x, 7 * mm, chunk)
            x += pdfmetrics.stringWidth(chunk, chunk_font, 7.5)
        canvas.setFont(FONT_VI, 7.5)
        canvas.drawRightString(A4[0] - MARGIN, 7 * mm, str(doc.page))
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=18 * mm,
                            title=f"{label('common.nav.keigo')} — {chapter}: {title}", author="毎日BJT")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _split_plain(text):
    """[(font, doan)] -- ban khong markup cua _runs, cho canvas.drawString."""
    out = []
    for ch in text:
        font = FONT_JP if _is_jp(ch) else FONT_VI
        if out and out[-1][0] == font:
            out[-1] = (font, out[-1][1] + ch)
        else:
            out.append((font, ch))
    return out
