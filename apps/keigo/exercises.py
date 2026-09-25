"""
Bai tap kinh ngu -- SC20 (danh sach), SC21 (lam bai), SC22 (ket qua).

Tach rieng khoi selectors.py (SC16-SC19) vi phan nay co GHI du lieu
(UserExerciseAttempt / UserQuestionAnswer / StudySession). views.py chi goi
ham o day, khong tu viet lai dieu kien loc hay cach cham diem.

Mockup Dat duyet: htmlTemplate/SC20_BaiTapDanhSach_A.html,
SC21_LamBai_A.html, SC22_KetQua_A.html -- doc cac quyet dinh o dau moi file.

Quy uoc du lieu (claude/keigo-thiet-ke.md muc 3):
  - stem_jp: cho trong `____`, o sao `__★__`, ruby `{漢字|かんじ}`.
  - Cho trong trong doan van danh so `（n）` khop Question.number.
  - Dang cloze: stem_jp chi la "(13)" -- cau that nam trong passage_jp.
  - Dang ordering: nguoi hoc chon VE vao o ★ (dung cach sach cham);
    correct_order chi dung de ghep lai cau hoan chinh khi hien dap an.
"""
import re
from dataclasses import dataclass, field

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe

from apps.core.constants import (
    QUESTION_TYPE_CLOZE,
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_ORDERING,
    SESSION_TYPE_KEIGO,
)
from apps.learning.models import StudySession

from .models import ExerciseSet, Question, UserExerciseAttempt, UserQuestionAnswer
from .templatetags.keigo_tags import RUBY_RE

# --- Tham so query string ----------------------------------------------------
LIST_VIEW_PARAM = "view"
LIST_VIEW_ALL = "all"
LIST_VIEW_TODO = "chua"
LIST_VIEW_DONE = "da"
LIST_VIEWS = (LIST_VIEW_ALL, LIST_VIEW_TODO, LIST_VIEW_DONE)

FEEDBACK_PARAM = "da"      # SC21: ?da=<question_id> -> hien phan hoi cau vua tra loi
ATTEMPT_PARAM = "lan"      # SC22: ?lan=<attempt_id> -> xem mot luot cu

RESULT_VIEW_PARAM = "view"
RESULT_VIEW_WRONG = "sai"
RESULT_VIEW_ALL = "tat-ca"
RESULT_VIEWS = (RESULT_VIEW_WRONG, RESULT_VIEW_ALL)

HISTORY_SIZE = 5

# Nguong mau diem -- dung chung SC20 va SC22.
LEVEL_HI = 80
LEVEL_MID = 50

# Thu tu hien chip dang cau hoi.
QUESTION_TYPE_ORDER = (QUESTION_TYPE_MCQ, QUESTION_TYPE_ORDERING, QUESTION_TYPE_CLOZE)

BLANK_NUMBER_RE = re.compile(r"[（(](\d{1,3})[）)]")
BLANK_MARK = "____"
STAR_MARK = "__★__"
# Cat doan van thanh cau: giu dau cau o cuoi, xuong dong cung la ranh gioi.
SENTENCE_RE = re.compile(r"[^。\n]+(?:。|$)")


def clean_choice(raw, allowed, default=None):
    return raw if raw in allowed else (default if default is not None else allowed[0])


def percent(score, total):
    return round(score * 100 / total) if total else 0


def score_level(score, total):
    p = percent(score, total)
    if p >= LEVEL_HI:
        return "hi"
    if p >= LEVEL_MID:
        return "mid"
    return "lo"


# =============================================================================
# Hien thi de: ruby + cho trong + o sao
# =============================================================================
def _ruby_escaped(text):
    """escape() TRUOC roi moi ghep <ruby> -- giong keigo_tags.ruby."""
    return RUBY_RE.sub(r"<ruby>\1<rt>\2</rt></ruby>", escape(text or ""))


def render_text(text, current=None, filled=None, ordering_fill=None, star_position=None, numbered=True):
    """Chuoi de (stem/passage/instruction) -> HTML an toan.

    current        : so cho trong dang lam -> to do.
    filled         : {so: (chu, "ok"|"ng")} cho trong da tra loi.
    ordering_fill  : list 4 (chu, so_in_sach) -> dien vao 4 o cua dang ★.
    star_position  : vi tri o ★ (1-4) khi dien ordering_fill.
    numbered=False : KHONG doi （n） thanh cho trong -- dung cho instruction_jp
                     (「（11）から（15）の中に…」 la loi dan, khong phai cho trong).
    Cho trong chua toi -> mo di.
    """
    filled = filled or {}
    html = _ruby_escaped(text)

    def number_blank(m):
        n = int(m.group(1))
        if n == current:
            return f'<span class="blank is-cur">（{n}）</span>'
        if n in filled:
            word, state = filled[n]
            return f'<span class="blank is-{state}">{escape(word)}</span>'
        return f'<span class="blank is-dim">（{n}）</span>'

    if numbered:
        html = BLANK_NUMBER_RE.sub(number_blank, html)

    if ordering_fill:
        slots = iter(ordering_fill)
        index = {"i": 0}

        def fill_slot(_m):
            index["i"] += 1
            word, number = next(slots, ("", ""))
            star = " is-star" if index["i"] == star_position else ""
            return f'<span class="slot is-filled{star}">{escape(word)}<sup>{number}</sup></span>'

        html = re.sub(r"__★__|____", fill_slot, html)
    else:
        html = html.replace(STAR_MARK, '<span class="slot is-star">★</span>')
        if html.count(BLANK_MARK) > 1:  # dang ★: 4 o
            html = html.replace(BLANK_MARK, '<span class="slot"></span>')
        else:
            html = html.replace(BLANK_MARK, '<span class="blank is-cur">？</span>')
    return mark_safe(html.replace("\n", "<br>"))


def sentence_with_blank(passage, number):
    """Cau trong passage chua cho trong (number) -- cho dang cloze, vi stem_jp
    chi la "(13)". Khong tim thay -> None."""
    for m in SENTENCE_RE.finditer(passage or ""):
        sentence = m.group(0).strip()
        for bm in BLANK_NUMBER_RE.finditer(sentence):
            if int(bm.group(1)) == number:
                return sentence
    return None


def question_sentence(question):
    """Than cau de hien trong the cau hoi / trang ket qua."""
    if question.question_type == QUESTION_TYPE_CLOZE:
        found = sentence_with_blank(question.section.passage_jp, question.number)
        if found:
            return found
    return question.stem_jp


def ordering_fill(question, options_by_position):
    """[(chu, so_in_sach), ...] theo correct_order -- None neu du lieu thieu."""
    order = (question.correct_order or "").strip()
    if sorted(order) != list("1234"):
        return None
    parts = []
    for d in order:
        opt = options_by_position.get(int(d))
        if opt is None:
            return None
        parts.append((opt.text_jp, d))
    return parts


# =============================================================================
# Truy van
# =============================================================================
def set_questions(exercise_set):
    """Moi cau cua mot bo, dung thu tu lam bai (section roi so cau)."""
    return list(
        Question.objects.filter(section__exercise_set=exercise_set)
        .select_related("section")
        .prefetch_related("options")
        .order_by("section__display_order", "section__number", "number", "pk")
    )


def open_attempt(user, exercise_set):
    """Luot DO DANG gan nhat cua user voi bo nay, hoac None."""
    return (UserExerciseAttempt.objects
            .filter(user=user, exercise_set=exercise_set, finished_at__isnull=True)
            .order_by("-started_at").first())


def finished_attempts(user, exercise_set):
    return (UserExerciseAttempt.objects
            .filter(user=user, exercise_set=exercise_set, finished_at__isnull=False)
            .order_by("-finished_at"))


def _type_counts(exercise_sets):
    """{set_id: {question_type: so cau}} + {set_id: so doan van} -- 2 truy van."""
    counts = {}
    rows = (Question.objects.filter(section__exercise_set__in=exercise_sets)
            .values("section__exercise_set", "question_type").annotate(n=Count("id")))
    for r in rows:
        counts.setdefault(r["section__exercise_set"], {})[r["question_type"]] = r["n"]
    passages = dict(
        ExerciseSet.objects.filter(pk__in=[s.pk for s in exercise_sets])
        .annotate(n=Count("sections", filter=~Q(sections__passage_jp="")))
        .values_list("pk", "n")
    )
    return counts, passages


@dataclass
class TypeChip:
    code: str
    count: int


@dataclass
class SetRow:
    exercise_set: ExerciseSet
    number_label: str
    question_total: int
    chips: list = field(default_factory=list)
    passage_count: int = 0
    # luot da xong
    attempt_count: int = 0
    best_score: int = 0
    best_total: int = 0
    last_attempt: object = None
    # luot do dang
    open_attempt: object = None
    open_answered: int = 0

    @property
    def is_done(self):
        return self.attempt_count > 0

    @property
    def best_percent(self):
        return percent(self.best_score, self.best_total)

    @property
    def level(self):
        return score_level(self.best_score, self.best_total)

    @property
    def open_percent(self):
        return percent(self.open_answered, self.question_total)

    @property
    def has_cloze(self):
        return any(c.code == QUESTION_TYPE_CLOZE for c in self.chips)


def list_rows(user):
    """17 dong SC20 -- so truy van co dinh, khong phu thuoc so bo."""
    sets = list(ExerciseSet.objects.order_by("display_order", "slug"))
    counts, passages = _type_counts(sets)

    done = {}
    for a in (UserExerciseAttempt.objects
              .filter(user=user, finished_at__isnull=False).order_by("-finished_at")):
        done.setdefault(a.exercise_set_id, []).append(a)
    opened = {}
    for a in (UserExerciseAttempt.objects
              .filter(user=user, finished_at__isnull=True)
              .annotate(answered=Count("answers")).order_by("-started_at")):
        opened.setdefault(a.exercise_set_id, a)

    rows, number = [], 0
    for s in sets:
        type_counts = counts.get(s.pk, {})
        # Bo co lesson=None va display_order nho nhat la LUYEN TAP (khong danh so)
        is_practice = s.slug == "luyen-tap"
        if not is_practice:
            number += 1
        row = SetRow(
            exercise_set=s,
            number_label="練" if is_practice else f"{number:02d}",
            question_total=sum(type_counts.values()),
            chips=[TypeChip(code, type_counts[code]) for code in QUESTION_TYPE_ORDER if type_counts.get(code)],
            passage_count=passages.get(s.pk, 0),
        )
        attempts = done.get(s.pk, [])
        if attempts:
            row.attempt_count = len(attempts)
            row.last_attempt = attempts[0]
            best = max(attempts, key=lambda a: (percent(a.score, a.total), a.score))
            row.best_score, row.best_total = best.score, best.total
        if s.pk in opened:
            row.open_attempt = opened[s.pk]
            row.open_answered = opened[s.pk].answered
        rows.append(row)
    return rows


def latest_open(rows):
    """Luot do dang MOI NHAT trong moi bo -- cho the "Dang lam do" o dau SC20."""
    candidates = [r for r in rows if r.open_attempt is not None]
    return max(candidates, key=lambda r: r.open_attempt.started_at) if candidates else None


def filter_rows(rows, view):
    if view == LIST_VIEW_TODO:
        return [r for r in rows if not r.is_done and r.open_attempt is None]
    if view == LIST_VIEW_DONE:
        return [r for r in rows if r.is_done]
    return rows


# =============================================================================
# Ghi du lieu
# =============================================================================
def start_attempt(user, exercise_set):
    """Tao luot moi -- tru khi bo nay da co luot do dang (tra ve luot do).

    Tra (attempt, created). attempt=None khi bo khong co cau nao."""
    existing = open_attempt(user, exercise_set)
    if existing is not None:
        return existing, False
    total = Question.objects.filter(section__exercise_set=exercise_set).count()
    if not total:
        return None, False
    attempt = UserExerciseAttempt.objects.create(
        user=user, exercise_set=exercise_set, score=0, total=total, started_at=timezone.now(),
    )
    return attempt, True


def record_answer(attempt, question, option):
    """Luu cau tra loi. Cau da tra loi roi -> KHONG ghi de (F5 / bam hai lan /
    hai tab). Tra (answer, created)."""
    existing = UserQuestionAnswer.objects.filter(attempt=attempt, question=question).first()
    if existing is not None:
        return existing, False
    try:
        with transaction.atomic():
            answer = UserQuestionAnswer.objects.create(
                attempt=attempt, question=question, selected_option=option,
                is_correct=bool(option.is_correct),
            )
    except IntegrityError:  # hai request cung luc
        return UserQuestionAnswer.objects.get(attempt=attempt, question=question), False
    attempt.score = attempt.answers.filter(is_correct=True).count()
    attempt.save(update_fields=["score", "updated_at", "updated_by"])
    return answer, True


def finish_attempt(attempt):
    """Chot luot: finished_at + diem + mot learning.StudySession de streak va
    bieu do o dashboard/SC15 dem ca phan kinh ngu (khong sua gamification)."""
    now = timezone.now()
    attempt.score = attempt.answers.filter(is_correct=True).count()
    attempt.finished_at = now
    attempt.save(update_fields=["score", "finished_at", "updated_at", "updated_by"])
    StudySession.objects.create(
        user=attempt.user,
        session_type=SESSION_TYPE_KEIGO,
        words_reviewed=attempt.total,
        correct_answers=attempt.score,
        started_at=attempt.started_at,
        ended_at=now,
    )
    return attempt


# =============================================================================
# SC21 -- trang thai mot cau
# =============================================================================
def progress(questions, answers_by_qid, current_id):
    """Dai o so tren dau SC21: [(thu_tu, "ok"|"ng"|"cur"|"")]."""
    out = []
    for i, q in enumerate(questions, start=1):
        a = answers_by_qid.get(q.pk)
        if a is not None:
            state = "ok" if a.is_correct else "ng"
        else:
            state = "cur" if q.pk == current_id else ""
        out.append((i, state))
    return out


def passage_fills(section_questions, answers_by_qid):
    """{so cho trong: (chu, trang thai)} cho cac cau da lam trong CUNG doan van.

    Dung -> hien dap an dung (xanh). Sai -> hien phuong an da chon (do)."""
    fills = {}
    for q in section_questions:
        a = answers_by_qid.get(q.pk)
        if a is None:
            continue
        if a.is_correct:
            fills[q.number] = (a.selected_option.text_jp if a.selected_option else "", "ok")
        else:
            fills[q.number] = (a.selected_option.text_jp if a.selected_option else "?", "ng")
    return fills


def decorate_options(question, answer=None):
    """Gan .state cho tung phuong an: ""(chua cham) / ok / ng / off."""
    opts = list(question.options.all())
    for o in opts:
        if answer is None:
            o.state = ""
        elif o.is_correct:
            o.state = "ok"
        elif answer.selected_option_id == o.pk:
            o.state = "ng"
        else:
            o.state = "off"
        o.picked = answer is not None and answer.selected_option_id == o.pk
    return opts


def correct_option(question):
    return next((o for o in question.options.all() if o.is_correct), None)


# =============================================================================
# SC22 -- ket qua
# =============================================================================
@dataclass
class ResultItem:
    question: Question
    order: int
    answer: object
    correct: object
    stem_html: str
    is_passage_excerpt: bool = False

    @property
    def is_correct(self):
        return self.answer is not None and self.answer.is_correct


def result_items(attempt, questions):
    answers = {a.question_id: a for a in
               attempt.answers.select_related("selected_option")}
    items = []
    for i, q in enumerate(questions, start=1):
        a = answers.get(q.pk)
        right = correct_option(q)
        if q.question_type == QUESTION_TYPE_ORDERING:
            fill = ordering_fill(q, {o.position: o for o in q.options.all()})
            stem = render_text(q.stem_jp, ordering_fill=fill, star_position=q.star_position) if fill \
                else render_text(q.stem_jp)
            excerpt = False
        else:
            sentence = question_sentence(q)
            stem = render_text(sentence, current=q.number)
            excerpt = q.question_type == QUESTION_TYPE_CLOZE and sentence != q.stem_jp
        items.append(ResultItem(question=q, order=i, answer=a, correct=right,
                                stem_html=stem, is_passage_excerpt=excerpt))
    return items


def type_breakdown(items):
    """[(question_type, dung, tong, level)] theo QUESTION_TYPE_ORDER."""
    out = []
    for code in QUESTION_TYPE_ORDER:
        group = [it for it in items if it.question.question_type == code]
        if group:
            ok = sum(1 for it in group if it.is_correct)
            out.append((code, ok, len(group), score_level(ok, len(group)), percent(ok, len(group))))
    return out


def previous_best(attempt):
    """Diem cao nhat cua CAC LUOT DA XONG TRUOC luot nay -- None neu la luot dau."""
    earlier = (UserExerciseAttempt.objects
               .filter(user=attempt.user, exercise_set=attempt.exercise_set,
                       finished_at__isnull=False, finished_at__lt=attempt.finished_at)
               .exclude(pk=attempt.pk))
    best = None
    for a in earlier:
        if best is None or percent(a.score, a.total) > percent(best.score, best.total):
            best = a
    return best


def next_set(exercise_set):
    return (ExerciseSet.objects
            .filter(Q(display_order__gt=exercise_set.display_order)
                    | Q(display_order=exercise_set.display_order, slug__gt=exercise_set.slug))
            .order_by("display_order", "slug").first())
