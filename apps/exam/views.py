"""
View khu Kiểm tra — docs/SPEC_KIEM_TRA.md mục 1.4. Mockup: htmlTemplate/SC23_KiemTra_A.html.

Mốc 1: S1 Tổng quan, S2 Tạo bài từ vựng, S3 Làm bài từ vựng, kết quả bài từ vựng.

Làm bài theo Post/Redirect/Get như bài tập kính ngữ (SC21): POST một câu ->
lưu -> chuyển sang GET ?da=<order> để hiện phản hồi. Có JS thì static/js/exam_play.js
gửi cùng form bằng fetch với header X-Exam-Partial: server trả thẳng trang phản
hồi thay vì redirect, JS thay khối #exam-play — không tải lại trang. Tắt JS vẫn
làm bài bình thường.
"""
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.core import quiz
from apps.core.constants import CODE_TYPE_VOCAB_QUESTION, EXAM_KIND_VOCAB, VOCAB_QUESTION_TYPES
from apps.core.mastercode import get_code_name
from apps.core.properties import message

from . import selectors
from .constants import SCOPE_DUE, SCOPE_MASTERED, SCOPE_TOPICS
from .forms import VocabSetupForm
from .models import ExamAttempt
from .services import attempts

FEEDBACK_PARAM = "da"
TYPE_PARAM = "dang"
PARTIAL_HEADER = "HTTP_X_EXAM_PARTIAL"


def _context(sub, **extra):
    return {"active_nav": "exam", "active_sub": sub, **extra}


def _int_or_none(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _own_attempt(request, attempt_id):
    """Lượt của CHÍNH người đang đăng nhập — người khác -> 404 (lọc ngay trong queryset)."""
    return get_object_or_404(ExamAttempt, pk=attempt_id, user=request.user)


def _play_url(attempt, feedback_order=None):
    url = reverse("exam:play", args=[attempt.pk])
    if feedback_order is not None:
        url += "?" + urlencode({FEEDBACK_PARAM: feedback_order})
    return url


# =============================================================================
# S1 — Tổng quan
# =============================================================================

@login_required
def hub_view(request):
    return render(request, "exam/hub.html", _context("hub", **selectors.hub(request.user)))


# =============================================================================
# S2 — Tạo bài từ vựng
# =============================================================================

@login_required
def vocab_setup_view(request):
    topics = selectors.learned_topics(request.user)
    initial = {}
    if request.GET.get(TYPE_PARAM) in VOCAB_QUESTION_TYPES:
        initial["types"] = [request.GET[TYPE_PARAM]]  # nút "Luyện <dạng yếu>" ở S1
    form = VocabSetupForm(request.POST or None, topics=topics, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        result = attempts.start_vocab_attempt(
            request.user,
            scope=data["scope"],
            topic_ids=[int(t) for t in data["topics"]] if data["scope"] == SCOPE_TOPICS else [],
            types=data["types"],
            count=data["count"],
            srs_link=data["srs_link"],
        )
        if result.not_enough is not None:
            flash.error(request, message("exam.vocab.error.not_enough", count=result.not_enough))
        else:
            if result.resumed:
                flash.info(request, message("exam.vocab.info.resumed"))
            return redirect("exam:play", attempt_id=result.attempt.pk)

    counts = selectors.scope_counts(request.user)
    context = _context(
        "vocab",
        form=form,
        topics=topics,
        selected_topics=set(form["topics"].value() or []),
        selected_types=set(form["types"].value() or []),
        counts=counts,
        scope_due=SCOPE_DUE, scope_topics=SCOPE_TOPICS, scope_mastered=SCOPE_MASTERED,
        resume=attempts.open_attempt(request.user, EXAM_KIND_VOCAB),
    )
    return render(request, "exam/vocab_setup.html", context)


# =============================================================================
# S3 — Làm bài
# =============================================================================

def _render_play(request, attempt, feedback=None, srs_effect=None):
    answers = list(attempt.answers.order_by("order"))
    unanswered = [a for a in answers if not a.is_answered]
    if feedback is None and not unanswered:
        feedback = answers[-1]  # làm hết rồi: hiện lại câu cuối + nút xem kết quả
    current = feedback or unanswered[0]
    options = current.payload.get("options") or []
    correct = current.payload.get("correct")
    rows = []
    for i, opt in enumerate(options, start=1):
        state = ""
        if current.is_answered:
            state = "ok" if i == correct else ("ng" if i == current.selected else "off")
        rows.append({"position": i, "text": opt["text"], "gloss": opt.get("gloss", ""), "state": state})

    answered = [a for a in answers if a.is_answered]
    context = _context(
        "vocab",
        attempt=attempt,
        answer=current,
        type_name=get_code_name(CODE_TYPE_VOCAB_QUESTION, current.question_type_code),
        options=rows,
        distractors=[r for r in rows if r["gloss"] and r["position"] != correct],
        correct_text=options[correct - 1]["text"] if correct and correct <= len(options) else "",
        srs_effect=srs_effect,
        total=len(answers),
        answered_count=len(answered),
        correct_count=sum(1 for a in answered if a.is_correct),
        progress_percent=quiz.percent(len(answered), len(answers)),
        is_last=not unanswered,
    )
    return render(request, "exam/play_vocab.html", context)


@login_required
def play_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if attempt.is_finished:
        return redirect("exam:result", attempt_id=attempt.pk)
    if attempt.kind_code != EXAM_KIND_VOCAB:
        raise Http404  # thi thử / dạng đề: mốc 2

    if request.method == "POST":
        order = _int_or_none(request.POST.get("order"))
        selected = _int_or_none(request.POST.get("option"))
        if order is None or selected is None:
            flash.error(request, message("exam.play.error.no_option"))
            return redirect(_play_url(attempt))
        result = attempts.answer(attempt, order, selected, _int_or_none(request.POST.get("t")) or 0)
        if result is None:
            return redirect(_play_url(attempt))
        if request.META.get(PARTIAL_HEADER):
            return _render_play(request, attempt, feedback=result.answer, srs_effect=result.srs_effect)
        if result.srs_effect:
            request.session[f"exam:srs:{attempt.pk}:{order}"] = result.srs_effect
        return redirect(_play_url(attempt, order))

    feedback = None
    order = _int_or_none(request.GET.get(FEEDBACK_PARAM))
    if order is not None:
        feedback = attempt.answers.filter(order=order, selected__isnull=False).first()
    effect = request.session.pop(f"exam:srs:{attempt.pk}:{order}", None) if feedback else None
    return _render_play(request, attempt, feedback=feedback, srs_effect=effect)


@login_required
@require_POST
def finish_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if not attempts.finish(attempt):
        flash.error(request, message("exam.play.error.not_finished"))
        return redirect(_play_url(attempt))
    return redirect("exam:result", attempt_id=attempt.pk)


@login_required
@require_POST
def abandon_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if attempts.abandon(attempt):
        flash.info(request, message("exam.play.info.abandoned"))
    return redirect("exam:vocab")


# =============================================================================
# Kết quả bài từ vựng
# =============================================================================

@login_required
def result_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if not attempt.is_finished:
        return redirect(_play_url(attempt))
    rows = selectors.answer_rows(attempt)
    wrong = [r for r in rows if not r.is_correct]
    context = _context(
        "vocab",
        attempt=selectors.decorate(attempt),
        rows=rows,
        wrong=wrong,
        breakdown=selectors.type_breakdown(rows),
        relearn_count=len(wrong) if attempt.scope.get("srs_link") else 0,
    )
    return render(request, "exam/result_vocab.html", context)
