"""Logic Học theo bài — view chỉ lắp context (spec.md rule 6). Spec: docs/SPEC_LUYEN_TAP_BAI.md.

L4 Mức lịch sự (◆4): một câu hỏi = MỘT BÀI có 2 câu khác mức — "câu nào trang trọng hơn?".
Mức 1/2/3 chỉ là thứ tự trong bài (xem T2), nên câu trang trọng hơn = level_code NHỎ hơn.
Dấu kết quả (UserPracticeMark kind=polite) đặt trên câu trang trọng hơn của cặp.
"""
import random

from django.utils import timezone

from apps.core.constants import PRACTICE_KIND_BLANK, PRACTICE_KIND_DRILL, PRACTICE_KIND_POLITE

from .models import BLANK_RE, DrillItem, Lesson, PolitenessPhrase, Roleplay, RoleplayBlank, Unit, UserPracticeMark

ROUND_SIZE = 10

# Bộ lọc chương của L4 (◆ mockup SC24): mã -> (chương đầu, chương cuối).
UNIT_GROUPS = {"all": (1, 12), "1-4": (1, 4), "5-8": (5, 8), "9-12": (9, 12)}
DEFAULT_GROUP = "all"


def clean_group(raw):
    return raw if raw in UNIT_GROUPS else DEFAULT_GROUP


def group_of_unit(number):
    return next(code for code, (lo, hi) in UNIT_GROUPS.items() if code != "all" and lo <= number <= hi)


# ---------------------------------------------------------------------------
# Cặp câu lịch sự
# ---------------------------------------------------------------------------

def pairs(lessons=None):
    """{lesson_id: (câu trang trọng hơn, câu thân mật hơn)} — chỉ bài có ĐÚNG 2 câu khác mức."""
    qs = PolitenessPhrase.objects.order_by("lesson_id", "level_code", "id")
    if lessons is not None:
        qs = qs.filter(lesson__in=lessons)
    grouped = {}
    for p in qs:
        grouped.setdefault(p.lesson_id, []).append(p)
    return {lid: (ps[0], ps[-1]) for lid, ps in grouped.items()
            if len(ps) == 2 and ps[0].level_code != ps[1].level_code}


def marks(user, kind, object_ids=None):
    """{object_id: is_known} của user cho một dạng câu."""
    qs = UserPracticeMark.objects.filter(user=user, kind=kind)
    if object_ids is not None:
        qs = qs.filter(object_id__in=object_ids)
    return dict(qs.values_list("object_id", "is_known"))


def build_round(user, group, rng=random):
    """10 bài cho một lượt, ưu tiên cặp đang sai -> cặp chưa làm -> cặp đã đúng.
    Trả dict lưu thẳng vào session: lesson id + câu nào hiện bên trái (flip)."""
    lo, hi = UNIT_GROUPS[clean_group(group)]
    lessons = Lesson.objects.filter(unit__number__gte=lo, unit__number__lte=hi)
    found = pairs(lessons)
    known = marks(user, PRACTICE_KIND_POLITE, [formal.id for formal, _ in found.values()])

    def bucket(lid):
        state = known.get(found[lid][0].id)
        return 0 if state is False else 1 if state is None else 2

    ids = list(found)
    rng.shuffle(ids)
    ids = sorted(ids, key=bucket)[:ROUND_SIZE]
    return {"group": clean_group(group), "ids": ids, "flips": [rng.random() < 0.5 for _ in ids], "answers": {}}


def round_question(state, i):
    """Câu thứ i (1-based) của lượt: bài, 2 lựa chọn theo thứ tự hiển thị, câu đúng."""
    lesson_id = state["ids"][i - 1]
    lesson = Lesson.objects.select_related("unit").get(pk=lesson_id)
    formal, casual = pairs([lesson])[lesson_id]
    options = [casual, formal] if state["flips"][i - 1] else [formal, casual]
    return {"lesson": lesson, "formal": formal, "casual": casual, "options": options}


def record(user, kind, object_id, is_known):
    """Kết quả GẦN NHẤT của một câu (◆3): ghi đè is_known, cộng số lần."""
    mark, _ = UserPracticeMark.objects.get_or_create(user=user, kind=kind, object_id=object_id)
    mark.is_known = is_known
    mark.times += 1
    mark.last_at = timezone.now()
    mark.save()
    return mark


# ---------------------------------------------------------------------------
# L2 Luyện thay thế (◆2: tự nói -> lật đáp án -> tự chấm)
# ---------------------------------------------------------------------------

def drill_queue(items, known, retry):
    """Câu sẽ hỏi: cả bài, hoặc (retry) chỉ câu chưa "Nói được"."""
    return [it for it in items if not retry or known.get(it.id) is not True]


def drill_step(queue, number):
    """(câu hiện tại, số câu kế tiếp hoặc None) — `number` lạ thì về câu đầu hàng đợi."""
    numbers = [it.number for it in queue]
    pos = numbers.index(number) if number in numbers else 0
    return queue[pos], (numbers[pos + 1] if pos + 1 < len(numbers) else None)


def next_drill_lesson(lesson):
    return Lesson.objects.filter(scene_no__gt=lesson.scene_no, drill__isnull=False).first()


# ---------------------------------------------------------------------------
# L3 Hội thoại đóng vai
# ---------------------------------------------------------------------------

def line_parts(text, blanks):
    """'スミスです。{1}。' -> [{'text': 'スミスです。'}, {'blank': <RoleplayBlank 1>}, {'text': '。'}].
    Không dựng HTML ở đây: template tự escape từng phần chữ, ô trống là thẻ của template.
    {n} không có đáp án giữ nguyên chữ (check_lesson_data báo lỗi loại này)."""
    parts, pos = [], 0
    for m in BLANK_RE.finditer(text):
        blank = blanks.get(int(m.group(1)))
        if blank is None:
            continue
        if m.start() > pos:
            parts.append({"text": text[pos:m.start()]})
        parts.append({"blank": blank})
        pos = m.end()
    if pos < len(text):
        parts.append({"text": text[pos:]})
    return parts


def roleplay_lines(roleplay):
    """Lời thoại đã tách phần + vai của người học (người nói câu có ô trống đầu tiên)."""
    blanks = {b.number: b for b in roleplay.blanks.all()}
    lines = [{"line": l, "parts": line_parts(l.text_jp, blanks)} for l in roleplay.lines.all()]
    me = next((r["line"].speaker for r in lines if any("blank" in p for p in r["parts"])), "")
    for r in lines:
        r["me"] = r["line"].speaker == me
    return lines, me, list(blanks.values())


def next_roleplay(roleplay):
    return (Roleplay.objects.select_related("unit")
            .filter(unit__number__gte=roleplay.unit.number)
            .exclude(unit__number=roleplay.unit.number, number__lte=roleplay.number)
            .order_by("unit__number", "number").first())


def next_retry_lesson(user, lesson):
    """Bài có drill kế tiếp còn câu "Chưa được" — nối chuỗi "Luyện lại câu chưa thuộc" (T8)."""
    ng = UserPracticeMark.objects.filter(user=user, kind=PRACTICE_KIND_DRILL, is_known=False).values("object_id")
    return (Lesson.objects.filter(scene_no__gt=lesson.scene_no, drill__items__id__in=ng)
            .order_by("scene_no").distinct().first())


# ---------------------------------------------------------------------------
# L1 Tổng quan
# ---------------------------------------------------------------------------

def overview(user):
    """12 chương kèm bài, tiến độ từng chương, thẻ "Học tiếp" và "Câu chưa thuộc" (T8)."""
    lessons = list(Lesson.objects.select_related("unit"))
    found = pairs()
    polite = marks(user, PRACTICE_KIND_POLITE, [f.id for f, _ in found.values()])
    drill_marks = marks(user, PRACTICE_KIND_DRILL)   # {item id: is_known}
    blank_marks = marks(user, PRACTICE_KIND_BLANK)   # {blank id: is_known}
    drill_items = {}
    for item_id, lesson_id in DrillItem.objects.values_list("id", "drill__lesson_id"):
        drill_items.setdefault(lesson_id, []).append(item_id)
    roleplay_blanks = {}
    for blank_id, roleplay_id in RoleplayBlank.objects.values_list("id", "roleplay_id"):
        roleplay_blanks.setdefault(roleplay_id, []).append(blank_id)

    units, rows_by_lesson, rp_by_id = [], {}, {}
    for unit in Unit.objects.prefetch_related("roleplays"):
        rows = []
        for lesson in (l for l in lessons if l.unit_id == unit.id):
            pair = found.get(lesson.id)
            items = drill_items.get(lesson.id, [])
            row = {
                "lesson": lesson,
                "has_drill": bool(items),
                "drill_known": sum(1 for i in items if drill_marks.get(i) is True),
                "drill_ng": sum(1 for i in items if drill_marks.get(i) is False),
                "drill_total": len(items),
                "has_polite": pair is not None,
                "polite_known": pair is not None and polite.get(pair[0].id) is True,
            }
            rows.append(row)
            rows_by_lesson[lesson.id] = row
        roleplays = []
        for rp in unit.roleplays.all():
            ids = roleplay_blanks.get(rp.id, [])
            r = {"roleplay": rp, "known": sum(1 for b in ids if blank_marks.get(b) is True),
                 "ng": sum(1 for b in ids if blank_marks.get(b) is False), "total": len(ids)}
            r["done"] = r["known"] == r["total"]
            roleplays.append(r)
            rp_by_id[rp.id] = r
        known = (sum(r["drill_known"] for r in rows) + sum(1 for r in rows if r["polite_known"])
                 + sum(r["known"] for r in roleplays))
        total = (sum(r["drill_total"] for r in rows) + sum(1 for r in rows if r["has_polite"])
                 + sum(r["total"] for r in roleplays))
        units.append({"unit": unit, "rows": rows, "roleplays": roleplays, "group": group_of_unit(unit.number),
                      "known": known, "total": total, "percent": round(100 * known / total) if total else 0})

    # Chương mở sẵn = chương đầu tiên còn câu chưa được ở bất kỳ dạng nào.
    open_unit = next((u["unit"].number for u in units if u["known"] < u["total"]), 1)
    # "Học tiếp" của từng thẻ: bài / đoạn đầu tiên còn câu chưa được (hết thì quay về cái đầu).
    drill_rows = [r for r in rows_by_lesson.values() if r["has_drill"]]
    all_roleplays = list(rp_by_id.values())
    next_drill = next((r for r in drill_rows if r["drill_known"] < r["drill_total"]), drill_rows[0] if drill_rows else None)
    next_rp = next((r for r in all_roleplays if not r["done"]), all_roleplays[0] if all_roleplays else None)

    return {
        "units": units,
        "open_unit": open_unit,
        "next_drill": next_drill and next_drill["lesson"],
        "next_roleplay": next_rp and next_rp["roleplay"],
        "resume": _resume(user, rows_by_lesson, rp_by_id, next_drill),
        "retry": {
            "drill": sum(1 for v in drill_marks.values() if v is False),
            "drill_lesson": next((r["lesson"] for r in drill_rows if r["drill_ng"]), None),
            "blank": sum(1 for v in blank_marks.values() if v is False),
            "roleplay": next((r["roleplay"] for r in all_roleplays if r["ng"]), None),
            "polite": sum(1 for v in polite.values() if v is False),
        },
        "stats": {
            "lessons": len(lessons),
            "drill_known": sum(r["drill_known"] for r in drill_rows),
            "drill_total": sum(r["drill_total"] for r in drill_rows),
            "blank_known": sum(r["known"] for r in all_roleplays),
            "blank_total": sum(r["total"] for r in all_roleplays),
            "polite_known": sum(1 for v in polite.values() if v),
            "polite_total": len(found),
        },
    }


def _resume(user, rows_by_lesson, rp_by_id, next_drill):
    """Thẻ "Học tiếp": bài / đoạn luyện gần nhất nếu còn câu chưa được, không thì bài drill chưa xong đầu tiên."""
    last = (UserPracticeMark.objects.filter(user=user, kind__in=[PRACTICE_KIND_DRILL, PRACTICE_KIND_BLANK])
            .order_by("-last_at").first())
    if last and last.kind == PRACTICE_KIND_DRILL:
        lesson_id = DrillItem.objects.filter(pk=last.object_id).values_list("drill__lesson_id", flat=True).first()
        row = rows_by_lesson.get(lesson_id)
        if row and row["drill_known"] < row["drill_total"]:
            return {"kind": "drill", "lesson": row["lesson"], "known": row["drill_known"],
                    "total": row["drill_total"], "at": last.last_at}
    elif last:
        roleplay_id = RoleplayBlank.objects.filter(pk=last.object_id).values_list("roleplay_id", flat=True).first()
        r = rp_by_id.get(roleplay_id)
        if r and not r["done"]:
            return {"kind": "roleplay", "roleplay": r["roleplay"], "known": r["known"], "total": r["total"],
                    "at": last.last_at}
    if next_drill and next_drill["drill_known"] < next_drill["drill_total"]:
        return {"kind": "drill", "lesson": next_drill["lesson"], "known": next_drill["drill_known"],
                "total": next_drill["drill_total"], "at": None}
    return None
