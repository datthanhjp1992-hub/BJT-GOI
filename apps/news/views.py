"""Nghe dịch bản tin — docs/SPEC_NGHE_BAN_TIN.md mục 5.

Chữ Nhật / bản dịch là <details> (ẩn sẵn, không cần JS). "Đã luyện" = POST done=1|0 tường minh
rồi redirect (PRG) — bấm lại hay F5 không lật trạng thái.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.constants import PRACTICE_KIND_NEWS
from apps.lessons import services as practice

from .models import NewsLesson
from .services import highlight, vocab_terms


@login_required
def index_view(request):
    lessons = list(NewsLesson.objects.all())
    done = practice.marks(request.user, PRACTICE_KIND_NEWS, [l.id for l in lessons])
    for lesson in lessons:
        lesson.done = done.get(lesson.id, False)
    return render(request, "news/index.html", {
        "lessons": lessons, "done_count": sum(l.done for l in lessons), "total": len(lessons),
        "active_nav": "news",
    })


@login_required
def lesson_view(request, number):
    lesson = get_object_or_404(NewsLesson, number=number)
    terms = vocab_terms()
    segments = list(lesson.segments.all())
    for seg in segments:
        seg.parts = highlight(seg.text_jp, terms)
    numbers = list(NewsLesson.objects.values_list("number", flat=True))
    i = numbers.index(number)
    return render(request, "news/lesson.html", {
        "lesson": lesson, "segments": segments,
        "done": practice.marks(request.user, PRACTICE_KIND_NEWS, [lesson.id]).get(lesson.id, False),
        "prev_number": numbers[i - 1] if i > 0 else None,
        "next_number": numbers[i + 1] if i + 1 < len(numbers) else None,
        "active_nav": "news",
    })


@login_required
@require_POST
def mark_view(request, number):
    lesson = get_object_or_404(NewsLesson, number=number)
    practice.record(request.user, PRACTICE_KIND_NEWS, lesson.id, request.POST.get("done") == "1")
    return redirect("news:lesson", number=number)
