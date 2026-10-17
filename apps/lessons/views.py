"""Học theo bài — L1 Tổng quan, L4 Mức lịch sự (Mốc 1). Mockup: htmlTemplate/SC24_LuyenTapBai_A.html.

L4 đi đúng khuôn kiểm tra chương của apps.grammar: lượt nằm trong session, ?i= là câu số mấy,
chấm bằng POST rồi redirect về chính câu đó (PRG — F5 không chấm lại), i > số câu thì hiện kết quả.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.constants import PRACTICE_KIND_POLITE

from . import services

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
