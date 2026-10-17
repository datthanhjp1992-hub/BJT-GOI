"""Logic Học theo bài — view chỉ lắp context (spec.md rule 6). Spec: docs/SPEC_LUYEN_TAP_BAI.md.

L4 Mức lịch sự (◆4): một câu hỏi = MỘT BÀI có 2 câu khác mức — "câu nào trang trọng hơn?".
Mức 1/2/3 chỉ là thứ tự trong bài (xem T2), nên câu trang trọng hơn = level_code NHỎ hơn.
Dấu kết quả (UserPracticeMark kind=polite) đặt trên câu trang trọng hơn của cặp.
"""
import random

from django.utils import timezone

from apps.core.constants import PRACTICE_KIND_BLANK, PRACTICE_KIND_DRILL, PRACTICE_KIND_POLITE

from .models import DrillItem, Lesson, PolitenessPhrase, RoleplayBlank, Unit, UserPracticeMark

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
# L1 Tổng quan
# ---------------------------------------------------------------------------

def overview(user):
    """12 chương kèm bài và trạng thái từng dạng luyện tập của user."""
    lessons = list(Lesson.objects.select_related("unit"))
    found = pairs()
    polite_known = marks(user, PRACTICE_KIND_POLITE, [f.id for f, _ in found.values()])
    drill_known = set(UserPracticeMark.objects.filter(user=user, kind=PRACTICE_KIND_DRILL, is_known=True)
                      .values_list("object_id", flat=True))
    drill_items = {}
    for item_id, lesson_id in DrillItem.objects.values_list("id", "drill__lesson_id"):
        drill_items.setdefault(lesson_id, []).append(item_id)

    units = []
    for unit in Unit.objects.prefetch_related("roleplays"):
        rows = []
        for lesson in (l for l in lessons if l.unit_id == unit.id):
            pair = found.get(lesson.id)
            items = drill_items.get(lesson.id, [])
            rows.append({
                "lesson": lesson,
                "has_drill": bool(items),
                "drill_known": sum(1 for i in items if i in drill_known),
                "drill_total": len(items),
                "has_polite": pair is not None,
                "polite_known": pair is not None and polite_known.get(pair[0].id) is True,
            })
        units.append({"unit": unit, "rows": rows, "group": group_of_unit(unit.number),
                      "polite_left": sum(1 for r in rows if r["has_polite"] and not r["polite_known"])})

    # Chương mở sẵn = chương đầu tiên còn cặp lịch sự chưa đúng (T5/T6 sẽ tính thêm drill, đóng vai).
    open_unit = next((u["unit"].number for u in units if u["polite_left"]), 1)
    return {
        "units": units,
        "open_unit": open_unit,
        "stats": {
            "lessons": len(lessons),
            "drill_known": len(drill_known),
            "drill_total": sum(len(v) for v in drill_items.values()),
            "blank_known": UserPracticeMark.objects.filter(user=user, kind=PRACTICE_KIND_BLANK, is_known=True).count(),
            "blank_total": RoleplayBlank.objects.count(),
            "polite_known": sum(1 for v in polite_known.values() if v),
            "polite_total": len(found),
        },
    }
