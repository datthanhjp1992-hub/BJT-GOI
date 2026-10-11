"""
View khu Kiểm tra — docs/SPEC_KIEM_TRA.md mục 1.4. Mockup: htmlTemplate/SC23_KiemTra_A.html.

Mốc 1: S1 Tổng quan, S2 Tạo bài từ vựng, S3 Làm bài từ vựng, kết quả bài từ vựng.
Mốc 2: S4 Chọn đề / dạng đề, S5–S6 Làm bài đề thi (Thi / Luyện), S7 Kết quả đề thi.

Làm bài theo Post/Redirect/Get như bài tập kính ngữ (SC21). Bài từ vựng: có JS thì
static/js/exam_play.js gửi bằng fetch với header X-Exam-Partial và thay khối #exam-play.
Đề thi: form POST thường (đồng hồ + khoá câu do server quyết, tải lại trang là chuẩn).
Tắt JS vẫn làm bài được ở mọi màn.
"""
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.core import quiz
from apps.core.constants import (
    CODE_TYPE_VOCAB_QUESTION,
    EXAM_KIND_DRILL,
    EXAM_KIND_MOCK,
    EXAM_KIND_VOCAB,
    EXAM_KIND_WRONGBOOK,
    EXAM_MODE_EXAM,
    EXAM_MODE_PRACTICE,
    VOCAB_QUESTION_TYPES,
)
from apps.core.mastercode import get_code_name
from apps.core.properties import message
from apps.learning import services as learning

from . import selectors
from .audio import exam_audio_url
from .constants import SCOPE_DUE, SCOPE_MASTERED, SCOPE_TOPICS
from .forms import VocabSetupForm
from .models import ExamAttempt, ExamSet
from .services import attempts, timing, wrongbook

FEEDBACK_PARAM = "da"      # ?da=<order>  -> phản hồi câu vừa trả lời (chế độ Luyện)
QUESTION_PARAM = "cau"     # ?cau=<order> -> mở một câu (phần Đọc / chế độ Luyện)
TYPE_PARAM = "dang"        # S2: ?dang=<dạng câu từ vựng> chọn sẵn
MODE_PARAM = "che-do"      # S4: chế độ Thi / Luyện
REVIEW_PARAM = "xem"       # S7: tab xem lại
REVIEW_TABS = ("sai", "co", "tat-ca")
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
    return get_object_or_404(ExamAttempt.objects.select_related("exam_set"), pk=attempt_id, user=request.user)


def _play_url(attempt, **params):
    url = reverse("exam:play", args=[attempt.pk])
    params = {k: v for k, v in params.items() if v is not None}
    return f"{url}?{urlencode(params)}" if params else url


def _sub_of(attempt):
    if attempt.kind_code == EXAM_KIND_WRONGBOOK:
        return "wrongbook"
    return "vocab" if attempt.kind_code == EXAM_KIND_VOCAB else "exam"


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
# S4 — Chọn đề / luyện dạng đề
# =============================================================================

@login_required
def exam_list_view(request):
    mode = request.GET.get(MODE_PARAM)
    if mode not in (EXAM_MODE_EXAM, EXAM_MODE_PRACTICE):
        mode = EXAM_MODE_EXAM
    return render(request, "exam/exam_list.html", _context(
        "exam",
        mode=mode, mode_exam=EXAM_MODE_EXAM, mode_practice=EXAM_MODE_PRACTICE,
        sets=selectors.exam_set_rows(request.user),
        sections=selectors.section_rows(request.user),
    ))


@login_required
@require_POST
def start_mock_view(request, set_slug):
    exam_set = get_object_or_404(ExamSet, slug=set_slug, is_active=True)
    mode = request.POST.get("mode")
    if mode not in (EXAM_MODE_EXAM, EXAM_MODE_PRACTICE):
        mode = EXAM_MODE_EXAM
    result = attempts.start_mock_attempt(request.user, exam_set, mode)
    if result.attempt is None:
        flash.error(request, message("exam.mock.error.empty"))
        return redirect("exam:exams")
    if result.resumed:
        flash.info(request, message("exam.mock.info.resumed", title=exam_set.title))
    return redirect("exam:play", attempt_id=result.attempt.pk)


@login_required
@require_POST
def start_drill_view(request, section_code):
    if section_code not in selectors.SECTION_ORDER:
        return redirect("exam:exams")
    result = attempts.start_drill_attempt(request.user, section_code)
    if result.attempt is None:
        flash.error(request, message("exam.mock.error.empty"))
        return redirect("exam:exams")
    if result.resumed:
        flash.info(request, message("exam.drill.info.resumed"))
    return redirect("exam:play", attempt_id=result.attempt.pk)


# =============================================================================
# S3 — Làm bài từ vựng
# =============================================================================

def _render_vocab(request, attempt, feedback=None, srs_effect=None):
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
        _sub_of(attempt),
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


def _play_vocab(request, attempt):
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
            return _render_vocab(request, attempt, feedback=result.answer, srs_effect=result.srs_effect)
        if result.srs_effect:
            request.session[f"exam:srs:{attempt.pk}:{order}"] = result.srs_effect
        return redirect(_play_url(attempt, da=order))

    feedback = None
    order = _int_or_none(request.GET.get(FEEDBACK_PARAM))
    if order is not None:
        feedback = attempt.answers.filter(order=order, selected__isnull=False).first()
    effect = request.session.pop(f"exam:srs:{attempt.pk}:{order}", None) if feedback else None
    return _render_vocab(request, attempt, feedback=feedback, srs_effect=effect)


# =============================================================================
# S5 / S6 — Làm bài đề thi (thi thử, luyện dạng đề)
# =============================================================================

def _pick_current(request, attempt, answers):
    """Câu đang hiện + có hiện đáp án không. answers đã select_related question."""
    by_order = {a.order: a for a in answers}
    if attempts.is_timed(attempt):
        part = attempt.current_part
        in_part = [a for a in answers if a.question.part == part]
        if part == timing.LISTENING_PART:
            current = by_order.get(attempts.cursor(attempt)) or in_part[0]
        else:
            wanted = by_order.get(_int_or_none(request.GET.get(QUESTION_PARAM)))
            current = wanted if wanted in in_part else next((a for a in in_part if not a.is_answered), in_part[0])
        return current, False

    feedback = by_order.get(_int_or_none(request.GET.get(FEEDBACK_PARAM)))
    if feedback is not None and feedback.is_answered:
        return feedback, True
    wanted = by_order.get(_int_or_none(request.GET.get(QUESTION_PARAM)))
    if wanted is not None:
        return wanted, wanted.is_answered
    unanswered = [a for a in answers if not a.is_answered]
    if unanswered:
        return unanswered[0], False
    return answers[-1], True  # làm hết: câu cuối + nút nộp bài


def _render_exam(request, attempt):
    answers = list(attempt.answers.select_related("question").prefetch_related("question__options").order_by("order"))
    current, show_answer = _pick_current(request, attempt, answers)
    q = current.question
    timed = attempts.is_timed(attempt)
    part = attempt.current_part if timed else None
    in_scope = [a for a in answers if part is None or a.question.part == part]
    idx = in_scope.index(current)
    listening_exam = timed and q.part == timing.LISTENING_PART
    answered = [a for a in answers if a.is_answered]
    parts = attempts.parts_of(attempt) if attempt.kind_code == EXAM_KIND_MOCK else []
    context = _context(
        _sub_of(attempt),
        attempt=selectors.decorate(attempt),
        answer=current,
        question=q,
        section_name=selectors.section_name(q.section_code),
        options=selectors.exam_options(current, show_answer),
        show_answer=show_answer,
        # Lời thoại bài nghe chỉ hiện khi được xem đáp án; văn bản đề bài luôn hiện.
        show_passage=bool(q.passage_jp) and (not q.passage_is_transcript or show_answer),
        passage_is_document=bool(q.passage_jp) and not q.passage_is_transcript,
        audio_url=exam_audio_url(q),
        audio_once=timed,
        audio_key=f"{attempt.pk}:{current.order}",
        timed=timed,
        listening_exam=listening_exam,
        locked=attempts.locked(attempt, current),
        seconds_left=timing.seconds_left(attempt, part) if timed else None,
        parts=[{"part": p, "name": selectors.section_name(f"p{p}"),
                "done": str(p) in attempt.part_submitted_at, "current": p == part} for p in parts],
        cells=selectors.nav_cells(attempt, answers, current, part),
        prev_order=in_scope[idx - 1].order if idx > 0 and not listening_exam else None,
        next_order=in_scope[idx + 1].order if idx + 1 < len(in_scope) else None,
        position=idx + 1,
        scope_total=len(in_scope),
        total=len(answers),
        answered_count=len(answered),
        correct_count=sum(1 for a in answered if a.is_correct),
        progress_percent=quiz.percent(len(answered), len(answers)),
        all_answered=len(answered) == len(answers),
        is_last_part=timed and part == max(parts),
    )
    return render(request, "exam/play_exam.html", context)


def _play_exam(request, attempt):
    attempts.refresh_timing(attempt)
    if attempt.is_finished:  # hết giờ phần cuối -> tự nộp
        flash.info(request, message("exam.mock.info.time_up"))
        return redirect("exam:result", attempt_id=attempt.pk)

    if request.method == "POST":
        order = _int_or_none(request.POST.get("order"))
        action = request.POST.get("action")
        if action == "flag" and order is not None:
            attempts.toggle_flag(attempt, order)
            return redirect(_play_url(attempt, cau=order))
        if action == "skip" and order is not None:
            attempts.skip(attempt, order)
            return redirect("exam:result", attempt_id=attempt.pk) if attempt.is_finished else redirect(_play_url(attempt))
        selected = _int_or_none(request.POST.get("option"))
        if order is None or selected is None:
            flash.error(request, message("exam.play.error.no_option"))
            return redirect(_play_url(attempt, cau=order))
        result = attempts.answer(attempt, order, selected, _int_or_none(request.POST.get("t")) or 0)
        if attempt.is_finished:
            return redirect("exam:result", attempt_id=attempt.pk)
        if result is None:
            flash.error(request, message("exam.play.error.locked"))
            return redirect(_play_url(attempt))
        if not attempts.is_timed(attempt):
            return redirect(_play_url(attempt, da=order))
        if result.answer.question.part == timing.LISTENING_PART:
            return redirect(_play_url(attempt))
        # Phần Đọc chế độ Thi: sang câu kế tiếp trong phần (chưa làm thì ưu tiên).
        nxt = (attempt.answers.filter(question__part=attempt.current_part, order__gt=order, selected__isnull=True)
               .order_by("order").first()
               or attempt.answers.filter(question__part=attempt.current_part, order__gt=order).order_by("order").first())
        return redirect(_play_url(attempt, cau=nxt.order if nxt else order))
    return _render_exam(request, attempt)


@login_required
def play_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if attempt.is_finished:
        return redirect("exam:result", attempt_id=attempt.pk)
    if attempts.is_vocab_attempt(attempt):
        return _play_vocab(request, attempt)
    return _play_exam(request, attempt)


@login_required
@require_POST
def submit_part_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    attempts.refresh_timing(attempt)
    attempts.submit_part(attempt)
    if attempt.is_finished:
        return redirect("exam:result", attempt_id=attempt.pk)
    return redirect(_play_url(attempt))


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
    kind = attempt.kind_code
    if attempts.abandon(attempt):
        flash.info(request, message("exam.play.info.abandoned"))
    return redirect({EXAM_KIND_VOCAB: "exam:vocab", EXAM_KIND_WRONGBOOK: "exam:wrongbook"}.get(kind, "exam:exams"))


# =============================================================================
# Kết quả
# =============================================================================

@login_required
def result_view(request, attempt_id):
    attempt = _own_attempt(request, attempt_id)
    if not attempt.is_finished:
        return redirect(_play_url(attempt))
    is_wrongbook = attempt.kind_code == EXAM_KIND_WRONGBOOK
    cleared = selectors.wrongbook_cleared_in(attempt) if is_wrongbook else 0
    if attempts.is_vocab_attempt(attempt):
        rows = selectors.answer_rows(attempt)
        wrong = [r for r in rows if not r.is_correct]
        return render(request, "exam/result_vocab.html", _context(
            _sub_of(attempt),
            attempt=selectors.decorate(attempt),
            rows=rows,
            wrong=wrong,
            breakdown=selectors.type_breakdown(rows),
            relearn_count=len(wrong) if attempt.scope.get("srs_link") else 0,
            is_wrongbook=is_wrongbook,
            cleared=cleared,
        ))

    rows = selectors.exam_review_rows(attempt)
    parts, sections = selectors.exam_breakdown(rows)
    tab = request.GET.get(REVIEW_PARAM)
    if tab not in REVIEW_TABS:
        tab = "sai"
    shown = {"sai": [r for r in rows if not r.is_correct],
             "co": [r for r in rows if r.flagged],
             "tat-ca": rows}[tab]
    prev = selectors.previous_attempt(attempt)
    decorated = selectors.decorate(attempt)
    scored = [s for s in sections if s["total"]]
    return render(request, "exam/result_exam.html", _context(
        _sub_of(attempt),
        is_wrongbook=is_wrongbook,
        cleared=cleared,
        attempt=decorated,
        parts=parts,
        sections=sections,
        weakest=min(scored, key=lambda s: s["percent"]) if scored else None,
        previous=prev,
        delta=decorated.percent - prev.percent if prev else None,
        delta_abs=abs(decorated.percent - prev.percent) if prev else None,
        rows=shown,
        tab=tab,
        tabs=[("sai", sum(1 for r in rows if not r.is_correct)), ("co", sum(1 for r in rows if r.flagged)),
              ("tat-ca", len(rows))],
        words=selectors.words_in_wrong(attempt),
        is_mock=attempt.kind_code == EXAM_KIND_MOCK,
        drill=EXAM_KIND_DRILL,
    ))


@login_required
@require_POST
def add_words_view(request, attempt_id):
    """S7 "Thêm từ trong câu sai vào ôn tập" — chỉ nhận từ nằm trong danh sách gợi ý."""
    attempt = _own_attempt(request, attempt_id)
    allowed = {v.pk: v for v in selectors.words_in_wrong(attempt)}
    picked = [allowed[i] for i in {_int_or_none(x) for x in request.POST.getlist("words")} if i in allowed]
    for vocab in picked:
        learning.get_or_start_progress(request.user, vocab)
    if picked:
        learning.invalidate_due_badge(request.user.pk)
        flash.success(request, message("exam.result.words_added", count=len(picked)))
    return redirect(reverse("exam:result", args=[attempt.pk]) + "#tu-moi")


# =============================================================================
# S8 — Sổ câu sai
# =============================================================================

@login_required
def wrongbook_view(request):
    tab = request.GET.get(REVIEW_PARAM)
    if tab not in selectors.WRONGBOOK_TABS:
        tab = selectors.WRONGBOOK_TABS[0]
    overview = selectors.wrongbook_overview(request.user)
    return render(request, "exam/wrongbook.html", _context(
        "wrongbook",
        tab=tab,
        tabs=[(code, overview["counts"][code]) for code in selectors.WRONGBOOK_TABS],
        rows=selectors.wrongbook_rows(request.user, tab),
        overview=overview,
        target_vocab=wrongbook.TARGET_VOCAB,
        target_exam=wrongbook.TARGET_EXAM,
        resume=attempts.open_attempt(request.user, EXAM_KIND_WRONGBOOK),
    ))


@login_required
@require_POST
def start_wrongbook_view(request, target):
    result = attempts.start_wrongbook_attempt(request.user, target)
    if result.attempt is None:
        flash.info(request, message("exam.wrongbook.info.nothing_due"))
        return redirect("exam:wrongbook")
    if result.resumed:
        flash.info(request, message("exam.wrongbook.info.resumed"))
    return redirect("exam:play", attempt_id=result.attempt.pk)
