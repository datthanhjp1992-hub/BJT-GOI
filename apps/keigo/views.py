"""
View cua app keigo -- SC16 (muc luc) + SC17 (bai hoc) + SC18 (bang tra dong tu)
+ SC19 (loi thuong gap).

SC20 (danh sach bai tap) + SC21 (lam bai) + SC22 (ket qua) -- 25/09/2026, logic
o apps/keigo/exercises.py. Chuong nao
khong co noi dung (meta_text rong) thi the tren SC16 van hien dang "sap co",
KHONG dan toi 404 -- dung quyet dinh 4 trong htmlTemplate/SC16_KinhNguMucLuc_A.html.

Ban quyen PDF (Thaolejp / HCC JAPAN) CHUA xin phep -- xem keigo-thiet-ke.md
muc 0. Cho toi khi Dat quyet, ca khu kinh ngu doi dang nhap, coi nhu tai lieu
hoc noi bo thay vi cong khai roi phai khoa lai sau.
"""
import logging

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.core.properties import label, message

from . import exercises
from . import pdf as keigo_pdf
from . import selectors
from .models import ExerciseSet, KeigoForm, KeigoLesson, KeigoPattern, KeigoVerb, Question

logger = logging.getLogger(__name__)

# Chuong duy nhat KHONG co trang bai hoc rieng -- no dan thang sang bang tra.
# Xem ghi chu 3 o dau htmlTemplate/SC16_KinhNguMucLuc_A.html.
VERB_TABLE_LESSON_SLUG = "bang-chia-dong-tu-bat-quy-tac"

# Bang 4 cot ma moi o co toi 4 dong thi rat dai -- 10 dong/trang du xem het
# 47 dong trong 5 trang, khong phai cuon qua nhieu.
PAGE_SIZE = 10


def _lesson_meta_text(lesson):
    """Dong "N mau ngu phap * N vi du * N cap tu" -- chi phan nao > 0 moi hien,
    tinh o Python thay vi lam 3 nhanh {% if %} noi nhau trong template."""
    parts = []
    if lesson.pattern_count:
        parts.append(f"{lesson.pattern_count} {label('keigo.index.lesson.pattern_count')}")
    if lesson.example_count:
        parts.append(f"{lesson.example_count} {label('keigo.index.lesson.example_count')}")
    if lesson.phrase_pair_count:
        parts.append(f"{lesson.phrase_pair_count} {label('keigo.index.lesson.pair_count')}")
    return " \u00b7 ".join(parts)


def _pagination_query(request):
    """Chuoi query giu lai q/loai/batquytac khi bam sang trang khac -- copy
    nguyen GET hien tai, chi bo `page`. Don gian hon
    apps/vocabulary/views.py._pagination_query() vi khong can chuan hoa lai
    gia tri, chi can mang nguyen ve."""
    params = QueryDict(mutable=True)
    params.update(request.GET)
    params.pop("page", None)
    encoded = params.urlencode()
    return ("&" + encoded) if encoded else ""


@login_required
def index_view(request):
    """SC16_KinhNguMucLuc."""
    lessons = list(
        KeigoLesson.objects.annotate(
            pattern_count=Count("patterns", distinct=True),
            example_count=Count("patterns__examples", distinct=True),
            phrase_pair_count=Count("phrase_pairs", distinct=True),
        )
    )
    for lesson in lessons:
        lesson.meta_text = _lesson_meta_text(lesson)
    totals = {
        "verb_count": KeigoVerb.objects.count(),
        "form_count": KeigoForm.objects.count(),
        "pattern_count": KeigoPattern.objects.count(),
    }
    context = {
        "lessons": lessons,
        "totals": totals,
        "verb_table_lesson_slug": VERB_TABLE_LESSON_SLUG,
        "active_nav": "keigo",
        "active_sub": "index",  # to dung muc "Muc luc" trong sidebar
    }
    return render(request, "keigo/index.html", context)


@login_required
def verb_lookup_view(request):
    """SC18_TraCuuDongTu -- loc + tim bang GET, khong bat buoc JavaScript.

    Phan trang PAGE_SIZE dong/trang -- bang 4 cot ma moi o co toi 4 dang thi
    47 dong roi ra rat dai. attach_columns() chi chay tren ĐUNG trang hien
    tai (page.object_list), khong phai toan bo verbs khop loc."""
    query = (request.GET.get(selectors.SEARCH_PARAM) or "").strip()
    style = selectors.clean_style(request.GET.get(selectors.STYLE_PARAM, ""))
    irregular_only = request.GET.get(selectors.IRREGULAR_PARAM) == "1"

    verbs_qs = selectors.filter_verbs(query=query, style=style, irregular_only=irregular_only)
    paginator = Paginator(verbs_qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    page.object_list = selectors.attach_columns(page.object_list)

    context = {
        "page_obj": page,
        "paginator": paginator,
        "pagination_query": _pagination_query(request),
        "query": query,
        "style": style,
        "irregular_only": irregular_only,
        "style_choices": selectors.style_filter_choices(),
        "total_verb_count": KeigoVerb.objects.count(),
        "active_nav": "keigo",
        "active_sub": "tra_cuu",  # to dung muc "Tra cuu tu" trong sidebar
    }
    return render(request, "keigo/tra_cuu.html", context)


@login_required
def verb_detail_view(request, pk):
    """Chi tiet mot dong tu -- trang RIENG (khong phai <details>) de chia se
    va de trang tu vung tro nguoc ve, xem ghi chu o cuoi
    htmlTemplate/SC18_TraCuuDongTu_A.html."""
    verb = get_object_or_404(KeigoVerb.objects.prefetch_related("forms"), pk=pk)
    verb = selectors.attach_columns([verb])[0]
    context = {"verb": verb, "active_nav": "keigo", "active_sub": "tra_cuu"}
    return render(request, "keigo/verb_detail.html", context)


def lesson_url(lesson):
    """URL "mo chuong nay" -- chuong bang chia dong tu di thang sang SC18."""
    if lesson.slug == VERB_TABLE_LESSON_SLUG:
        return reverse("keigo:tra_cuu")
    return reverse("keigo:lesson", args=[lesson.slug])


def _lesson_position(lesson):
    """(tat ca chuong theo thu tu, vi tri 0-based cua `lesson`)."""
    lessons = list(KeigoLesson.objects.order_by("display_order", "slug"))
    position = next(i for i, x in enumerate(lessons) if x.pk == lesson.pk)
    return lessons, position


@login_required
def learn_start_view(request):
    """Muc "Hoc tu" o sidebar -- vao chuong dau tien co trang bai hoc. La
    redirect chu khong hardcode slug trong sidebar.html, de doi thu tu chuong
    qua SC07b khong phai sua template."""
    lesson = (KeigoLesson.objects.exclude(slug=VERB_TABLE_LESSON_SLUG)
              .order_by("display_order", "slug").first())
    if lesson is None:
        return redirect("keigo:index")
    return redirect("keigo:lesson", slug=lesson.slug)


@login_required
def lesson_view(request, slug):
    """SC17_BaiHoc -- phuong an 3: danh sach muc ben trai, moi lan hien MOT
    muc; truoc/sau la link GET ?muc=<key>. Het muc cuoi thi "tiep" dan sang
    chuong sau. Xem selectors.lesson_items()."""
    lesson = get_object_or_404(KeigoLesson, slug=slug)
    if lesson.slug == VERB_TABLE_LESSON_SLUG:
        return redirect("keigo:tra_cuu")

    base_url = reverse("keigo:lesson", args=[lesson.slug])
    items = selectors.lesson_items(lesson)
    for item in items:
        item.url = f"{base_url}?{urlencode({selectors.LESSON_ITEM_PARAM: item.key})}"

    lessons, position = _lesson_position(lesson)
    prev_lesson = lessons[position - 1] if position > 0 else None
    next_lesson = lessons[position + 1] if position + 1 < len(lessons) else None
    for other in (prev_lesson, next_lesson):
        if other is not None:
            other.url = lesson_url(other)

    index, current = None, None
    prev_item = next_item = None
    if items:
        index, current = selectors.pick_item(items, request.GET.get(selectors.LESSON_ITEM_PARAM, ""))
        selectors.load_item_detail(lesson, current)
        prev_item = items[index - 1] if index > 0 else None
        next_item = items[index + 1] if index + 1 < len(items) else None

    context = {
        "lesson": lesson,
        "lesson_number": position + 1,
        "lesson_total": len(lessons),
        "stats": selectors.lesson_stats(lesson),
        "items": items,
        "current": current,
        "position": (index + 1) if items else 0,
        "pattern_total": sum(1 for i in items if i.kind == selectors.KIND_PATTERN),
        "prev_item": prev_item,
        "next_item": next_item,
        "prev_lesson": prev_lesson,
        "next_lesson": next_lesson,
        "active_nav": "keigo",
        "active_sub": "hoc_tu",  # to dung muc "Hoc tu" trong sidebar
    }
    return render(request, "keigo/lesson.html", context)


@login_required
def lesson_pdf_view(request, slug):
    """Nut "In on tap chuong nay" o SC17 -- PDF TOAN BO noi dung chuong.

    GET, khong ghi gi vao DB nen la link <a> binh thuong. Tra `inline` de
    trinh duyet mo san trong tab moi: xem, in giay hay luu file deu duoc.
    Sinh moi moi lan (vai tram dong, duoi 1 giay), khong luu vao MEDIA_ROOT --
    MEDIA_ROOT tren Render la ephemeral, va du lieu sua qua SC07b thi PDF tu
    cap nhat theo."""
    lesson = get_object_or_404(KeigoLesson, slug=slug)
    if lesson.slug == VERB_TABLE_LESSON_SLUG:
        return redirect("keigo:tra_cuu")
    lessons, position = _lesson_position(lesson)
    try:
        data = keigo_pdf.build_lesson_pdf(lesson, position + 1, len(lessons))
    except keigo_pdf.KeigoPdfFontError:
        logger.exception("Thieu font khi sinh PDF on tap kinh ngu")
        flash.error(request, message("keigo.pdf.error.font_missing"))
        return redirect("keigo:lesson", slug=lesson.slug)
    response = HttpResponse(data, content_type="application/pdf")
    filename = keigo_pdf.lesson_pdf_filename(lesson, position + 1)
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _pitfall_url(view, check, query=""):
    """URL SC19 giu ?an=1 khi doi tab / bo tim kiem."""
    params = {selectors.PITFALL_VIEW_PARAM: view}
    if query:
        params[selectors.SEARCH_PARAM] = query
    if check:
        params[selectors.PITFALL_CHECK_PARAM] = "1"
    return f"{reverse('keigo:loi_thuong_gap')}?{urlencode(params)}"


@login_required
def pitfall_view(request):
    """SC19_LoiThuongGap -- 87 cap tu KeigoPhrasePair gom theo pair_type.

    Tab ?view=, tim ?q= (quet ca 8 nhom), tu kiem tra ?an=1 -- tat ca la GET,
    khong JavaScript. Xem selectors.pitfall_page() va 7 quyet dinh o dau
    htmlTemplate/SC19_LoiThuongGap_A.html."""
    query = (request.GET.get(selectors.SEARCH_PARAM) or "").strip()
    check = request.GET.get(selectors.PITFALL_CHECK_PARAM) == "1"
    data = selectors.pitfall_page(view=request.GET.get(selectors.PITFALL_VIEW_PARAM, ""), query=query)

    # "Xem trong chuong N" -- N la VI TRI chuong (giong "Chuong N / 7" o SC17),
    # link toi dung muc cap-<pair_type> cua SC17.
    positions = {pk: i for i, pk in enumerate(
        KeigoLesson.objects.order_by("display_order", "slug").values_list("pk", flat=True), start=1)}
    for t in data["types"]:
        t.url = _pitfall_url(t.code, check)
    for t in data["shown"]:
        if t.lesson is not None:
            t.lesson_number = positions.get(t.lesson.pk, 0)
            t.lesson_url = (f"{reverse('keigo:lesson', args=[t.lesson.slug])}?"
                            f"{urlencode({selectors.LESSON_ITEM_PARAM: selectors.PAIR_ITEM_PREFIX + t.code})}")

    context = {
        **data,
        "query": query,
        "check": check,
        "clear_url": _pitfall_url(data["view"], check),
        "check_toggle_url": _pitfall_url(data["view"], not check, query),
        "active_nav": "keigo",
        "active_sub": "loi_thuong_gap",  # to dung muc "Loi thuong gap" trong sidebar
    }
    return render(request, "keigo/loi_thuong_gap.html", context)


# =============================================================================
# SC20-SC22 -- Bai tap kinh ngu (25/09/2026). Logic o exercises.py.
# Tao/xoa/chot luot deu la POST (<button> trong <form>), xem va lam tiep la GET.
# =============================================================================
def _exercise_context(**extra):
    return {"active_nav": "keigo", "active_sub": "bai_tap", **extra}


def _play_url(exercise_set, feedback_question=None):
    url = reverse("keigo:bai_tap_lam", args=[exercise_set.slug])
    if feedback_question is not None:
        url += "?" + urlencode({exercises.FEEDBACK_PARAM: feedback_question.pk})
    return url


@login_required
def exercise_list_view(request):
    """SC20_BaiTapDanhSach -- 17 bo de, diem cao nhat, luot do dang."""
    view = exercises.clean_choice(request.GET.get(exercises.LIST_VIEW_PARAM, ""), exercises.LIST_VIEWS)
    rows = exercises.list_rows(request.user)
    done_count = sum(1 for r in rows if r.is_done)
    todo_count = sum(1 for r in rows if not r.is_done and r.open_attempt is None)
    tabs = [
        (exercises.LIST_VIEW_ALL, label("keigo.exercise.list.tab.all"), len(rows)),
        (exercises.LIST_VIEW_TODO, label("keigo.exercise.list.tab.todo"), todo_count),
        (exercises.LIST_VIEW_DONE, label("keigo.exercise.list.tab.done"), done_count),
    ]
    context = _exercise_context(
        rows=exercises.filter_rows(rows, view),
        all_rows=rows,
        view=view,
        tabs=[(code, name, n, f"{reverse('keigo:bai_tap')}?{urlencode({exercises.LIST_VIEW_PARAM: code})}")
              for code, name, n in tabs],
        resume=exercises.latest_open(rows),
        set_count=len(rows),
        question_count=sum(r.question_total for r in rows),
        done_count=done_count,
        is_new=not any(r.is_done or r.open_attempt for r in rows),
        first_set=rows[0].exercise_set if rows else None,
    )
    return render(request, "keigo/bai_tap.html", context)


@login_required
@require_POST
def exercise_start_view(request, set_slug):
    """Nut "Bat dau" / "Lam lai" / "Bo tiep theo" -- tao luot (hoac quay ve luot do dang)."""
    exercise_set = get_object_or_404(ExerciseSet, slug=set_slug)
    attempt, _created = exercises.start_attempt(request.user, exercise_set)
    if attempt is None:
        flash.error(request, message("keigo.exercise.error.empty_set"))
        return redirect("keigo:bai_tap")
    return redirect("keigo:bai_tap_lam", set_slug=exercise_set.slug)


@login_required
@require_POST
def exercise_abandon_view(request, set_slug):
    """"Bo luot nay" -- xoa luot do dang (cau tra loi CASCADE theo)."""
    exercise_set = get_object_or_404(ExerciseSet, slug=set_slug)
    deleted, _ = exercises.UserExerciseAttempt.objects.filter(
        user=request.user, exercise_set=exercise_set, finished_at__isnull=True).delete()
    if deleted:
        flash.info(request, message("keigo.exercise.info.abandoned", title=exercise_set.title))
    return redirect("keigo:bai_tap")


@login_required
def exercise_play_view(request, set_slug):
    """SC21_LamBai -- moi lan MOT cau, cham ngay (Post/Redirect/Get).

    GET            : cau CHUA tra loi dau tien cua luot do dang.
    GET ?da=<id>   : phan hoi cau vua tra loi (dap an, giai thich neu co).
    POST           : question + option -> luu, redirect ?da=<question id>.
    Het cau        : hien phan hoi cau cuoi voi nut "Xem ket qua" (POST nop/).
    """
    exercise_set = get_object_or_404(ExerciseSet, slug=set_slug)
    attempt = exercises.open_attempt(request.user, exercise_set)
    if attempt is None:
        flash.info(request, message("keigo.exercise.info.no_open_attempt", title=exercise_set.title))
        return redirect("keigo:bai_tap")

    questions = exercises.set_questions(exercise_set)
    if not questions:
        flash.error(request, message("keigo.exercise.error.empty_set"))
        return redirect("keigo:bai_tap")
    by_id = {q.pk: q for q in questions}

    if request.method == "POST":
        question = by_id.get(_int_or_none(request.POST.get("question")))
        if question is None:
            return redirect(_play_url(exercise_set))
        option = next((o for o in question.options.all()
                       if o.pk == _int_or_none(request.POST.get("option"))), None)
        if option is None:
            flash.error(request, message("keigo.exercise.error.no_option"))
            return redirect(_play_url(exercise_set))
        exercises.record_answer(attempt, question, option)
        return redirect(_play_url(exercise_set, question))

    answers = {a.question_id: a for a in attempt.answers.select_related("selected_option")}
    unanswered = [q for q in questions if q.pk not in answers]

    feedback_q = by_id.get(_int_or_none(request.GET.get(exercises.FEEDBACK_PARAM)))
    if feedback_q is not None and feedback_q.pk not in answers:
        feedback_q = None  # ?da= tro toi cau chua lam -> coi nhu khong co
    if feedback_q is None and not unanswered:
        feedback_q = questions[-1]  # lam het roi: hien lai cau cuoi + nut xem ket qua

    current = feedback_q or unanswered[0]
    answer = answers.get(current.pk)
    section = current.section
    section_questions = [q for q in questions if q.section_id == section.pk]

    fills = exercises.passage_fills(section_questions, answers)
    fills.pop(current.number, None)
    if answer is not None:
        # Cau dang xem phan hoi: dien luon vao cho trong cua chinh no.
        chosen = answer.selected_option.text_jp if answer.selected_option else "?"
        fills[current.number] = (chosen, "ok" if answer.is_correct else "ng")

    is_ordering = current.question_type == exercises.QUESTION_TYPE_ORDERING
    options = exercises.decorate_options(current, answer)
    order_fill = None
    if is_ordering and answer is not None:
        order_fill = exercises.ordering_fill(current, {o.position: o for o in options})
    sentence = exercises.question_sentence(current)
    if order_fill:
        stem_html = exercises.render_text(current.stem_jp, ordering_fill=order_fill,
                                          star_position=current.star_position)
    elif answer is not None and exercises.BLANK_MARK in sentence and not is_ordering:
        stem_html = exercises.render_text(
            sentence.replace(exercises.BLANK_MARK, f"（{current.number}）", 1),
            current=None, filled={current.number: fills[current.number]})
    else:
        stem_html = exercises.render_text(sentence, current=None if answer else current.number,
                                          filled=fills)

    position = questions.index(current) + 1
    next_q = unanswered[0] if unanswered else None
    context = _exercise_context(
        exercise_set=exercise_set,
        attempt=attempt,
        question=current,
        answer=answer,
        options=options,
        is_ordering=is_ordering,
        stem_html=stem_html,
        instruction_html=exercises.render_text(section.instruction_jp, numbered=False),
        passage_html=(exercises.render_text(section.passage_jp, current=None if answer else current.number,
                                            filled=fills) if section.passage_jp else ""),
        order_text=" → ".join(current.correct_order) if order_fill else "",
        correct=exercises.correct_option(current),
        position=position,
        total=len(questions),
        answered_count=len(answers),
        correct_count=sum(1 for a in answers.values() if a.is_correct),
        progress=exercises.progress(questions, answers, current.pk),
        next_question=next_q,
        is_last=next_q is None,
    )
    return render(request, "keigo/lam_bai.html", context)


def _int_or_none(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@login_required
@require_POST
def exercise_finish_view(request, set_slug):
    """Nut "Xem ket qua" o cau cuoi -- chot luot roi sang SC22."""
    exercise_set = get_object_or_404(ExerciseSet, slug=set_slug)
    attempt = exercises.open_attempt(request.user, exercise_set)
    if attempt is None:
        return redirect("keigo:bai_tap_ket_qua", set_slug=exercise_set.slug)
    total = Question.objects.filter(section__exercise_set=exercise_set).count()
    if attempt.answers.count() < total:
        flash.error(request, message("keigo.exercise.error.not_finished"))
        return redirect(_play_url(exercise_set))
    exercises.finish_attempt(attempt)
    url = reverse("keigo:bai_tap_ket_qua", args=[exercise_set.slug])
    return redirect(f"{url}?{urlencode({exercises.ATTEMPT_PARAM: attempt.pk})}")


@login_required
def exercise_result_view(request, set_slug):
    """SC22_KetQua -- mac dinh luot DA XONG gan nhat, ?lan=<id> xem luot cu.

    Luot cua nguoi khac -> 404: loc theo user NGAY trong queryset."""
    exercise_set = get_object_or_404(ExerciseSet, slug=set_slug)
    finished = exercises.finished_attempts(request.user, exercise_set)
    attempt_id = request.GET.get(exercises.ATTEMPT_PARAM)
    if attempt_id:
        attempt = finished.filter(pk=_int_or_none(attempt_id)).first()
        if attempt is None:
            raise Http404
    else:
        attempt = finished.first()
        if attempt is None:
            return redirect("keigo:bai_tap")

    view = exercises.clean_choice(request.GET.get(exercises.RESULT_VIEW_PARAM, ""), exercises.RESULT_VIEWS)
    questions = exercises.set_questions(exercise_set)
    items = exercises.result_items(attempt, questions)
    wrong = [it for it in items if not it.is_correct]
    best_before = exercises.previous_best(attempt)
    base = reverse("keigo:bai_tap_ket_qua", args=[exercise_set.slug])

    def tab_url(code):
        return f"{base}?{urlencode({exercises.ATTEMPT_PARAM: attempt.pk, exercises.RESULT_VIEW_PARAM: code})}"

    history = list(finished[:exercises.HISTORY_SIZE])
    order = {pk: n for n, pk in enumerate(
        finished.order_by("finished_at").values_list("pk", flat=True), start=1)}
    for a in history:
        a.number = order.get(a.pk)
        a.level = exercises.score_level(a.score, a.total)
        a.percent = exercises.percent(a.score, a.total)
        a.url = f"{base}?{urlencode({exercises.ATTEMPT_PARAM: a.pk})}"

    minutes = max(1, round((attempt.finished_at - attempt.started_at).total_seconds() / 60))
    context = _exercise_context(
        exercise_set=exercise_set,
        attempt=attempt,
        attempt_number=order.get(attempt.pk),
        percent=exercises.percent(attempt.score, attempt.total),
        level=exercises.score_level(attempt.score, attempt.total),
        minutes=minutes,
        best_before=best_before,
        is_record=best_before is not None and exercises.percent(attempt.score, attempt.total)
        > exercises.percent(best_before.score, best_before.total),
        breakdown=exercises.type_breakdown(items),
        view=view,
        items=items if view == exercises.RESULT_VIEW_ALL else wrong,
        wrong_count=len(wrong),
        item_count=len(items),
        tab_wrong_url=tab_url(exercises.RESULT_VIEW_WRONG),
        tab_all_url=tab_url(exercises.RESULT_VIEW_ALL),
        history=history,
        next_set=exercises.next_set(exercise_set),
    )
    return render(request, "keigo/ket_qua.html", context)
