from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.keigo.views import _pagination_query

from . import services
from .models import GrammarPattern, chapter_name_vi

PAGE_SIZE = 20


def _session_key(category):
    return f"grammar_quiz:{category}"


def _chapter(category):
    patterns = list(GrammarPattern.objects.filter(category=category))
    if not patterns:
        raise Http404
    names = [c for c, _ in services.ordered_chapters()]
    return patterns, names.index(category) + 1


def _index(request, total):
    """?i= (1-based) kẹp vào [1, total]."""
    try:
        return min(max(int(request.GET.get("i", 1)), 1), total)
    except ValueError:
        return 1


@login_required
def index_view(request):
    """Lưới chương có tiến độ; có ?q= thì thành trang kết quả tìm trên cả 500 mẫu."""
    query = (request.GET.get("q") or "").strip()
    context = {"query": query, "total_count": GrammarPattern.objects.count(), "active_nav": "grammar"}
    if query:
        qs = GrammarPattern.objects.filter(
            Q(pattern__icontains=query) | Q(meaning_vi__icontains=query) | Q(example_jp__icontains=query)
        )
        paginator = Paginator(qs, PAGE_SIZE)
        context.update(
            page_obj=paginator.get_page(request.GET.get("page")),
            paginator=paginator,
            pagination_query=_pagination_query(request),
        )
    else:
        mastered = services.mastered_by_chapter(request.user)
        context["chapters"] = [
            {"no": i, "jp": c, "vi": chapter_name_vi(c), "count": n, "mastered": mastered.get(c, 0),
             "percent": round(100 * mastered.get(c, 0) / n)}
            for i, (c, n) in enumerate(services.ordered_chapters(), start=1)
        ]
        context["mastered_total"] = sum(mastered.values())
    return render(request, "grammar/index.html", context)


@login_required
def chapter_view(request, category):
    """Học từng mẫu: một mẫu một màn hình, ?i= chọn mẫu, có trước/sau."""
    patterns, no = _chapter(category)
    i = _index(request, len(patterns))
    pattern = patterns[i - 1]
    mastered = services.mastered_ids(request.user, patterns)
    context = {
        "pattern": pattern,
        "i": i,
        "total": len(patterns),
        "percent": round(100 * i / len(patterns)),
        "is_mastered": pattern.id in mastered,
        "mastered_count": len(mastered),
        "no": no,
        "jp": category,
        "vi": chapter_name_vi(category),
        "active_nav": "grammar",
    }
    return render(request, "grammar/chapter.html", context)


@login_required
def quiz_view(request, category):
    """Kiểm tra cuối chương: ?i= là câu số mấy; câu đã trả lời thì hiện đúng/sai.
    ?moi=1 làm lại từ đầu; i > số câu thì hiện kết quả."""
    patterns, no = _chapter(category)
    key = _session_key(category)
    if request.GET.get("moi") or key not in request.session:
        request.session[key] = {}
        if request.GET.get("moi"):
            return redirect(reverse("grammar:quiz", args=[category]))
    answers = request.session[key]
    context = {"no": no, "jp": category, "vi": chapter_name_vi(category), "total": len(patterns),
               "active_nav": "grammar"}

    try:
        i = int(request.GET.get("i", 1))
    except ValueError:
        i = 1
    if i > len(patterns):
        wrong = [(n, p) for n, p in enumerate(patterns, start=1) if answers.get(str(p.id)) != p.id]
        context.update(result=True, score=len(patterns) - len(wrong), wrong=wrong)
        return render(request, "grammar/quiz.html", context)

    i = max(i, 1)
    pattern = patterns[i - 1]
    chosen = answers.get(str(pattern.id))
    context.update(
        i=i,
        percent=round(100 * (i - 1) / len(patterns)),
        question=services.build_question(pattern, patterns),
        chosen=chosen,
        answered=chosen is not None,
        is_correct=chosen == pattern.id,
        pattern=pattern,
        score=sum(1 for p in patterns if answers.get(str(p.id)) == p.id),
    )
    return render(request, "grammar/quiz.html", context)


@login_required
@require_POST
def quiz_answer_view(request, category):
    """Chấm một câu rồi redirect về chính câu đó (PRG — F5 không chấm lại)."""
    patterns, _ = _chapter(category)
    try:
        i = int(request.POST["i"])
        chosen = int(request.POST["option"])
        pattern = patterns[i - 1]
    except (KeyError, ValueError, IndexError):
        return redirect(reverse("grammar:quiz", args=[category]))
    answers = request.session.setdefault(_session_key(category), {})
    if str(pattern.id) not in answers:
        answers[str(pattern.id)] = chosen
        request.session.modified = True
        services.record_answer(request.user, pattern, chosen == pattern.id)
    return redirect(f"{reverse('grammar:quiz', args=[category])}?i={i}")
