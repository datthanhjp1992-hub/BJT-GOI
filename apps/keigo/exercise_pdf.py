"""
SC20 -- PDF DE BAI TAP kinh ngu (nut "⎙ PDF" tren moi dong bo de).

Muc dich: in ra giay de lam bai khong can may. Thu tu giong SC21 (set_questions):
  - Trang dau: tieu de bo de + dong "Ho ten / Ngay / Diem" de dien tay.
  - Tung phan: loi dan 問題 (chi in khi KHAC phan truoc -- LUYEN TAP 問題3 va
    BAI TAP 12 問題2 bi tach thanh nhieu section cung loi dan), doan van (neu
    co), roi tung cau + phuong an.
  - TRANG CUOI RIENG: bang dap an (PageBreak) -- khong muon lo dap an thi chi
    in cac trang truoc.

Quy uoc hien thi (claude/keigo-thiet-ke.md muc 3), ban giay:
  - `____` 1 cho -> （　　　　）;  dang ★: 4 o `＿＿＿`, o sao `＿★＿`.
  - Cau co doan van ma cho trong （n） NAM TRONG doan van (cloze, LUYEN TAP 問題3)
    -> chi in "（n）" + phuong an, khong chep lai cau (da co trong doan van).
  - Ruby {漢字|かんじ} -> 漢字(かんじ) nhu PDF on tap chuong.

Font + chan trang dung chung apps/keigo/pdf.py (IPAGothic + DejaVu, xem ghi chu
o dau file do). Thieu font -> KeigoPdfFontError, view bao loi, khong chet site.
"""
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle

from apps.core.constants import QUESTION_TYPE_ORDERING
from apps.core.properties import label

from . import exercises
from .pdf import (
    ACCENT, FONT_VI, INK, MARGIN, PANEL, RULE, SOFT,
    _ensure_fonts, _grid, _mk, _runs, _styles, build_document,
)

# Cho trong ban giay. KHONG dung khoang trang toan goc U+3000: Paragraph coi no
# la whitespace va gop lai con mot dau cach -> "（ ）" hep. Dung NBSP (DejaVu).
PAPER_BLANK_INNER = "\u00a0" * 14
PAPER_SLOT = "＿＿＿"
PAPER_STAR = "＿★＿"
SECTION_LABEL_RE = re.compile(r"^\s*(問題\s*\d*)")

# Chon so cot phuong an theo do dai dai nhat (so ky tu).
OPTION_COLS = ((6, 4), (14, 2))


def exercise_pdf_filename(exercise_set):
    return f"kinh-ngu-bai-tap-{exercise_set.slug}.pdf"


def _ex_styles():
    st = _styles()
    base = dict(fontName=FONT_VI, textColor=INK)
    st.update({
        "instr": ParagraphStyle("instr", fontSize=10.5, leading=16, spaceBefore=12, spaceAfter=6,
                                textColor=ACCENT, fontName=FONT_VI),
        "passage": ParagraphStyle("passage", fontSize=10.5, leading=18, **base),
        "q": ParagraphStyle("q", fontSize=11, leading=18, leftIndent=9 * mm, firstLineIndent=-9 * mm,
                            spaceBefore=7, **base),
        "opt": ParagraphStyle("opt", fontSize=10.5, leading=15, **base),
        "key_head": ParagraphStyle("key_head", fontSize=8.5, leading=11, textColor=SOFT, fontName=FONT_VI),
    })
    return st


# --- Chuoi de -> markup Paragraph ----------------------------------------------

def paper_text(text, numbered_bold=True):
    """stem/passage/instruction -> markup Paragraph cho ban in.

    Cat THEO ky hieu truoc (____ / __★__ / （n）), roi moi _mk() tung doan -- de
    escape va chia font khong lam vo ky hieu."""
    text = str(text or "")
    star = text.count(exercises.STAR_MARK)
    blanks = text.replace(exercises.STAR_MARK, "").count(exercises.BLANK_MARK)
    # Khong dung <b>: font dang ky rieng le, khong phai family -> reportlab
    # khong tim duoc ban dam. Dam = _runs(bold=True) (DejaVu Bold cho so).
    token_re = re.compile(r"__★__|____|[（(]\d{1,3}[）)]")
    out, pos = [], 0
    for m in token_re.finditer(text):
        out.append(_mk(text[pos:m.start()]))
        tok = m.group(0)
        if tok == exercises.STAR_MARK:
            out.append(f'<font color="#B5432E">{_runs(PAPER_STAR)}</font>')
        elif tok == exercises.BLANK_MARK:
            # Dang ★ (co o sao hoac nhieu o) -> o gach; mot cho duy nhat -> （　　）.
            if star or blanks > 1:
                out.append(_runs(PAPER_SLOT))
            else:
                out.append(f"{_runs('（')}{_runs(PAPER_BLANK_INNER)}{_runs('）')}")
        else:
            n = exercises.BLANK_NUMBER_RE.match(tok).group(1)
            out.append(_runs(f"（{n}）", bold=numbered_bold))
        pos = m.end()
    out.append(_mk(text[pos:]))
    return "".join(out).replace("\n", "<br/>")


def _blank_in_passage(question):
    passage = question.section.passage_jp or ""
    return any(int(m.group(1)) == question.number for m in exercises.BLANK_NUMBER_RE.finditer(passage))


def section_label(section):
    """"問題2" lay tu dau loi dan; khong co thi 問題<number>."""
    m = SECTION_LABEL_RE.match(section.instruction_jp or "")
    return m.group(1).replace(" ", "") if m else f"問題{section.number}"


def group_sections(questions):
    """[(section_dau, [(section, [cau...]), ...])] -- gop cac section LIEN NHAU
    co cung loi dan thanh mot nhom (một 問題 bi tach thanh N doan van)."""
    groups = []
    for q in questions:
        sec = q.section
        if not groups or groups[-1][0].instruction_jp != sec.instruction_jp:
            groups.append((sec, []))
        parts = groups[-1][1]
        if not parts or parts[-1][0].pk != sec.pk:
            parts.append((sec, []))
        parts[-1][1].append(q)
    return groups


# --- Flowable ------------------------------------------------------------------

def _options_table(options, st, width):
    if not options:
        return None
    longest = max(len(o.text_jp) for o in options)
    cols = next((c for limit, c in OPTION_COLS if longest <= limit), 1)
    cells = [Paragraph(f'<font color="#6b6455">{_runs(str(o.position))}</font>　{_mk(o.text_jp)}', st["opt"])
             for o in options]
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    rows[-1] += [""] * (cols - len(rows[-1]))
    indent = 9 * mm
    t = Table([[""] + r for r in rows], colWidths=[indent] + [(width - indent) / cols] * cols, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t


def question_flowables(question, st, width):
    if question.section.passage_jp and _blank_in_passage(question):
        # Cau da nam trong doan van ngay tren -> chi in so cho trong, khong "2. （2）".
        line = _runs(f"（{question.number}）", bold=True)
    else:
        line = f"{_runs(f'{question.number}.')}\u00a0\u00a0"
        if question.context_note:  # （レストランで） -- cung dong, mau nhat
            line += f'<font color="#6b6455">{_mk(question.context_note)}</font> '
        line += paper_text(question.stem_jp, numbered_bold=False)
    head = [Paragraph(line, st["q"])]
    table = _options_table(list(question.options.all()), st, width)
    # Cau + phuong an khong tach trang.
    return [KeepTogether(head + ([Spacer(1, 2), table] if table else []))]


def _passage_box(section, st, width):
    t = Table([[Paragraph(paper_text(section.passage_jp), st["passage"])]], colWidths=[width], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [Spacer(1, 4), t, Spacer(1, 2)]


def _answer_text(question):
    """(so phuong an dung, markup noi dung) -- dang ★ them thu tu day du nhu sach: 3(1234)."""
    right = exercises.correct_option(question)
    if right is None:
        return "—", ""
    shown = _mk(right.text_jp)
    if question.question_type == QUESTION_TYPE_ORDERING:
        fill = exercises.ordering_fill(question, {o.position: o for o in question.options.all()})
        if fill:
            order = _runs(" → ".join(d for _w, d in fill))
            sentence = "".join(w for w, _d in fill)
            shown += (f'<br/><font size="8.5" color="#6b6455">{_runs(label("keigo.exercise.play.order_prefix"))}'
                      f" {order} · {_mk(sentence)}</font>")
    return str(right.position), shown


def answer_key_flowables(groups, st, width):
    out = [
        Paragraph(_runs(label("keigo.exercise.pdf.key.eyebrow")), st["kicker"]),
        Paragraph(_runs(label("keigo.exercise.pdf.key.title")), st["h2"]),
    ]
    show_group = len(groups) > 1
    for sec, parts in groups:
        rows = [[Paragraph(_runs(label(k)), st["key_head"]) for k in (
            "keigo.exercise.pdf.key.col.question", "keigo.exercise.pdf.key.col.answer",
            "keigo.exercise.pdf.key.col.content")]]
        for _s, qs in parts:
            for q in qs:
                pos, shown = _answer_text(q)
                if q.explanation_vi:
                    shown += f'<br/><font size="8.5" color="#6b6455">{_mk(q.explanation_vi)}</font>'
                rows.append([Paragraph(_runs(str(q.number)), st["cell"]),
                             Paragraph(_runs(pos, bold=True), st["cell_acc"]),
                             Paragraph(shown, st["cell"])])
        table = _grid(rows, [14 * mm, 16 * mm, width - 30 * mm], [("LINEBELOW", (0, 0), (-1, 0), 0.8, SOFT)])
        table.repeatRows = 1  # bang dai sang trang -> lap lai dong tieu de cot
        head = [Paragraph(_runs(section_label(sec)), st["sub"])] if show_group else []
        # Nhan 問題N khong mo coi cuoi trang.
        out.append(KeepTogether(head + [table]))
    return out


def _name_line(st, width, total):
    cells = [f'{_runs(label("keigo.exercise.pdf.name"))}', f'{_runs(label("keigo.exercise.pdf.date"))}',
             f'{_runs(label("keigo.exercise.pdf.score"))}{_runs(chr(0xa0) * 12 + f"/ {total}")}']
    t = Table([[Paragraph(c, st["meta"]) for c in cells]], colWidths=[width * 0.5, width * 0.28, width * 0.22],
              hAlign="LEFT")
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _type_name(code):
    return label({"ordering": "keigo.exercise.type.ordering",
                  "cloze": "keigo.exercise.type.cloze"}.get(code, "keigo.exercise.type.mcq_blank"))


def build_exercise_pdf(exercise_set, questions=None):
    """Bytes PDF de + dap an cua mot bo. Nem KeigoPdfFontError neu thieu font."""
    _ensure_fonts()
    st = _ex_styles()
    width = A4[0] - 2 * MARGIN
    if questions is None:
        questions = exercises.set_questions(exercise_set)
    groups = group_sections(questions)
    total = len(questions)

    counts = {}
    for q in questions:
        counts[q.question_type] = counts.get(q.question_type, 0) + 1
    meta = [f'{total} {label("keigo.exercise.list.question_unit")}'] + [
        f"{_type_name(code)} · {counts[code]}" for code in exercises.QUESTION_TYPE_ORDER if counts.get(code)]

    story = [
        Paragraph(_runs(f'毎日BJT · {label("common.nav.keigo")} · {label("keigo.exercise.list.title")}'), st["brand"]),
        Paragraph(_runs(exercise_set.title), st["title"]),
        Paragraph(_runs(" · ".join(meta)), st["meta"]),
        _name_line(st, width, total),
        Spacer(1, 4),
    ]
    for sec, parts in groups:
        if sec.instruction_jp:
            story.append(Paragraph(paper_text(sec.instruction_jp, numbered_bold=False), st["instr"]))
        for part, qs in parts:
            if part.passage_jp:
                story.extend(_passage_box(part, st, width))
            for q in qs:
                story.extend(question_flowables(q, st, width))

    story.append(PageBreak())
    story.extend(answer_key_flowables(groups, st, width))

    title = f'{label("keigo.exercise.list.title")} — {exercise_set.title}'
    return build_document(story, title=title, footer_text=f"毎日BJT — {title}")

