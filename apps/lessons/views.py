"""Học theo bài — L1 Tổng quan, L2 Luyện thay thế, L3 Đóng vai, L4 Mức lịch sự.
Mockup: htmlTemplate/SC24_LuyenTapBai_A.html.

L2/L3 tự chấm (◆2) không cần JS: "Hiện đáp án" / ô trống là <details>, nút "Nói được / Chưa được"
POST rồi redirect (PRG). Kết quả chỉ giữ lần gần nhất của từng câu (◆3, UserPracticeMark).

L4 đi đúng khuôn kiểm tra chương của apps.grammar: lượt nằm trong session, ?i= là câu số mấy,
chấm bằng POST rồi redirect về chính câu đó (PRG — F5 không chấm lại), i > số câu thì hiện kết quả.
"""
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.constants import PRACTICE_KIND_BLANK, PRACTICE_KIND_DRILL, PRACTICE_KIND_POLITE

from . import services
from .models import DrillItem, Lesson, Roleplay, RoleplayBlank

SESSION_KEY = "lessons_polite_round"


def _polite_url(group, **extra):
    query = "&".join(f"{k}={v}" for k, v in {"chuong": group, **extra}.items())
    return f"{reverse('lessons:polite')}?{query}"


@login_required
def index_view(request):
    context = {**services.overview(request.user), "active_nav": "lessons", "active_sub": "index"}
    return render(request, "lessons/index.html", context)


@login_required
def polite_view(request):
    group = services.clean_group(request.GET.get("chuong"))
    state = request.session.get(SESSION_KEY)
    if request.GET.get("moi") or not state or state.get("group") != group:
        request.session[SESSION_KEY] = services.build_round(request.user, group)
        if request.GET.get("moi"):
            return redirect(_polite_url(group))
        state = request.session[SESSION_KEY]

    total = len(state["ids"])
    context = {"group": group, "groups": list(services.UNIT_GROUPS), "total": total,
               "active_nav": "lessons", "active_sub": "polite"}
    if not total:
        return render(request, "lessons/polite.html", {**context, "empty": True})

    try:
        i = max(int(request.GET.get("i", 1)), 1)
    except ValueError:
        i = 1
    answers = state["answers"]
    score = sum(1 for v in answers.values() if v)
    if i > total:
        items = []
        for lesson_id in state["ids"]:
            q = services.round_question(state, state["ids"].index(lesson_id) + 1)
            items.append({**q, "ok": answers.get(str(lesson_id))})
        return render(request, "lessons/polite.html",
                      {**context, "result": True, "score": score, "percent": round(100 * score / total),
                       "items": items})

    i = min(i, total)
    question = services.round_question(state, i)
    answered = str(question["lesson"].id) in answers
    context.update(
        i=i, question=question, answered=answered, is_correct=answers.get(str(question["lesson"].id)),
        score=score, percent=round(100 * (i - 1) / total),
    )
    return render(request, "lessons/polite.html", context)


@login_required
@require_POST
def polite_answer_view(request):
    state = request.session.get(SESSION_KEY)
    try:
        i = int(request.POST["i"])
        chosen = int(request.POST["option"])
        question = services.round_question(state, i)
    except (KeyError, ValueError, IndexError, TypeError):
        return redirect(reverse("lessons:polite"))
    key = str(question["lesson"].id)
    if key not in state["answers"]:
        ok = chosen == question["formal"].id
        state["answers"][key] = ok
        request.session.modified = True
        services.record(request.user, PRACTICE_KIND_POLITE, question["formal"].id, ok)
    return redirect(_polite_url(state["group"], i=i))


# ---------------------------------------------------------------------------
# L2 Luyện thay thế — ?n= số câu, ?lai=1 chỉ câu chưa được, ?xong=1 trang kết quả
# ---------------------------------------------------------------------------

def _drill_url(scene_no, **query):
    url = reverse("lessons:drill", args=[scene_no])
    return f"{url}?{'&'.join(f'{k}={v}' for k, v in query.items())}" if query else url


@login_required
def drill_view(request, scene_no):
    lesson = get_object_or_404(Lesson.objects.select_related("unit", "drill"), scene_no=scene_no,
                               drill__isnull=False)
    items = list(lesson.drill.items.all())
    if not items:
        raise Http404
    known = services.marks(request.user, PRACTICE_KIND_DRILL, [it.id for it in items])
    retry = request.GET.get("lai") == "1"
    queue = services.drill_queue(items, known, retry)
    context = {
        "lesson": lesson, "drill": lesson.drill, "items": items, "known": known, "retry": retry,
        "said": sum(1 for v in known.values() if v), "seen": bool(known),
        "active_nav": "lessons", "active_sub": "index",
    }
    if request.GET.get("xong") or not queue:
        rows = [{"item": it, "ok": known.get(it.id)} for it in items]
        context.update(done=True, rows=rows, any_left=any(r["ok"] is not True for r in rows),
                       next_lesson=services.next_drill_lesson(lesson))
        return render(request, "lessons/drill.html", context)

    try:
        number = int(request.GET.get("n", 0))
    except ValueError:
        number = 0
    current, next_number = services.drill_step(queue, number)
    context.update(current=current, next_number=next_number,
                   dots=[{"item": it, "ok": known.get(it.id), "cur": it == current} for it in items])
    return render(request, "lessons/drill.html", context)


@login_required
@require_POST
def drill_mark_view(request, scene_no):
    try:
        item = DrillItem.objects.get(pk=int(request.POST["item"]), drill__lesson__scene_no=scene_no)
        ok = request.POST["ok"] == "1"
    except (KeyError, ValueError, DrillItem.DoesNotExist):
        return redirect(_drill_url(scene_no))
    services.record(request.user, PRACTICE_KIND_DRILL, item.id, ok)
    query = {"lai": 1} if request.POST.get("lai") == "1" else {}
    nxt = request.POST.get("next", "")
    query.update({"n": int(nxt)} if nxt.isdigit() else {"xong": 1})
    return redirect(_drill_url(scene_no, **query))


# ---------------------------------------------------------------------------
# L3 Hội thoại đóng vai — ?mo=1,3 ô đang mở (vừa chấm), ?all=1 mở tất cả
# ---------------------------------------------------------------------------

def _open_numbers(raw):
    return sorted({int(x) for x in (raw or "").split(",") if x.isdigit()})


@login_required
def roleplay_view(request, unit_no, number):
    roleplay = get_object_or_404(Roleplay.objects.select_related("unit"), unit__number=unit_no, number=number)
    lines, me, blanks = services.roleplay_lines(roleplay)
    known = services.marks(request.user, PRACTICE_KIND_BLANK, [b.id for b in blanks])
    for b in blanks:
        b.state = known.get(b.id)  # True / False / None (chưa chấm) — template tô nút ✓ ✗
    opened = _open_numbers(request.GET.get("mo"))
    return render(request, "lessons/roleplay.html", {
        "roleplay": roleplay, "unit": roleplay.unit, "lines": lines, "me": me, "known": known,
        "show_all": request.GET.get("all") == "1", "opened": opened,
        "opened_str": ",".join(map(str, opened)),
        "said": sum(1 for b in blanks if known.get(b.id)), "total": len(blanks),
        "siblings": roleplay.unit.roleplays.all(), "next_roleplay": services.next_roleplay(roleplay),
        "active_nav": "lessons", "active_sub": "index",
    })


@login_required
@require_POST
def roleplay_mark_view(request, unit_no, number):
    url = reverse("lessons:roleplay", args=[unit_no, number])
    try:
        blank = RoleplayBlank.objects.get(pk=int(request.POST["blank"]), roleplay__unit__number=unit_no,
                                          roleplay__number=number)
        ok = request.POST["ok"] == "1"
    except (KeyError, ValueError, RoleplayBlank.DoesNotExist):
        return redirect(url)
    services.record(request.user, PRACTICE_KIND_BLANK, blank.id, ok)
    opened = ",".join(map(str, sorted(set(_open_numbers(request.POST.get("mo"))) | {blank.number})))
    query = f"mo={opened}" + ("&all=1" if request.POST.get("all") == "1" else "")
    return redirect(f"{url}?{query}#o{blank.number}")
