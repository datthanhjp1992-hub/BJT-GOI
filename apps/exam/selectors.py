"""
Truy vấn chỉ đọc của khu Kiểm tra — S1 Tổng quan, S2 Tạo bài, S4 Chọn đề, kết quả (S7).
Ghi dữ liệu nằm ở apps/exam/services/.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.core import quiz
from apps.core.constants import (
    CODE_TYPE_EXAM_KIND,
    CODE_TYPE_EXAM_MODE,
    CODE_TYPE_EXAM_SECTION,
    CODE_TYPE_VOCAB_QUESTION,
    EXAM_KIND_DRILL,
    EXAM_KIND_MOCK,
    EXAM_KIND_VOCAB,
    EXAM_KIND_WRONGBOOK,
)
from apps.core.mastercode import get_code_name
from apps.core.properties import label
from apps.learning.models import UserVocabularyProgress
from apps.vocabulary.models import Topic, Vocabulary

from .constants import (
    KANA_LINE_SLUG_SUFFIX,
    RECENT_RESULTS,
    SCOPE_DUE,
    SCOPE_MASTERED,
    VOCAB_MIN_WORDS,
    WEAK_SPOT_COUNT,
    WEAK_SPOT_DAYS,
    WEAK_SPOT_MIN_ANSWERS,
)
from .audio import exam_audio_url
from .models import ExamAnswer, ExamAttempt, ExamQuestion, ExamSet, WrongBookEntry
from .services import attempts, vocab_quiz, wrongbook

# Thứ tự hiển thị 8 dạng đề (MasterCode 20).
SECTION_ORDER = ("p1s1", "p1s2", "p1s3", "p2s1", "p2s2", "p3s1", "p3s2", "p3s3")


def decorate(attempt):
    """Gắn số liệu hiển thị cho một lượt: %, mức màu, tên loại."""
    attempt.percent = quiz.percent(attempt.score, attempt.total)
    attempt.level = quiz.score_level(attempt.score, attempt.total)
    attempt.kind_name = get_code_name(CODE_TYPE_EXAM_KIND, attempt.kind_code)
    attempt.mode_name = get_code_name(CODE_TYPE_EXAM_MODE, attempt.mode_code)
    attempt.title = attempt.kind_name
    if attempt.kind_code == EXAM_KIND_MOCK and attempt.exam_set_id:
        attempt.title = f"{attempt.kind_name} · {attempt.exam_set.title}"
    elif attempt.kind_code == EXAM_KIND_DRILL:
        attempt.title = f"{attempt.kind_name} · {section_name(attempt.section_code)}"
    elif attempt.kind_code == EXAM_KIND_WRONGBOOK:
        target = label("exam.wrongbook.target.vocab" if attempt.scope.get("target") == wrongbook.TARGET_VOCAB
                       else "exam.wrongbook.target.exam")
        attempt.title = f"{attempt.kind_name} · {target}"
    attempt.duration_text = ""
    if attempt.finished_at:
        attempt.duration_text = format_duration((attempt.finished_at - attempt.started_at).total_seconds())
    return attempt


def format_duration(seconds):
    """1:38:20 / 4:12 — giống cột thời gian ở mockup S1."""
    seconds = max(0, int(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def resume_attempt(user):
    """Lượt dở mới nhất kèm tiến độ, None nếu không có."""
    attempt = attempts.open_attempt(user)
    if attempt is None:
        return None
    attempt.answered = attempt.answers.filter(selected__isnull=False).count()
    return decorate(attempt)


def recent_results(user, limit=RECENT_RESULTS):
    rows = (ExamAttempt.objects.filter(user=user, finished_at__isnull=False).select_related("exam_set")
            .order_by("-finished_at")[:limit])
    return [decorate(a) for a in rows]


def section_name(code):
    return get_code_name(CODE_TYPE_EXAM_SECTION, code)


def section_accuracy(user, now=None):
    """{section_code: {"total", "correct", "percent", "level"}} — câu đề thi đã làm trong 30 ngày."""
    since = (now or timezone.now()) - timedelta(days=WEAK_SPOT_DAYS)
    rows = (
        ExamAnswer.objects.filter(attempt__user=user, answered_at__gte=since, question__isnull=False)
        .values("question__section_code")
        .annotate(n=Count("pk"), ok=Count("pk", filter=Q(is_correct=True)))
    )
    return {
        r["question__section_code"]: {"total": r["n"], "correct": r["ok"], "percent": quiz.percent(r["ok"], r["n"]),
                                      "level": quiz.score_level(r["ok"], r["n"])}
        for r in rows
    }


def weak_spots(user, now=None):
    """Dạng câu đúng thấp nhất trong 30 ngày (mỗi dạng cần >= 5 câu): dạng câu từ vựng
    (MasterCode 23) và dạng đề BJT (MasterCode 20). kind cho template biết nút luyện trỏ đâu."""
    spots = [
        {"kind": EXAM_KIND_DRILL, "code": code, "name": section_name(code), **acc}
        for code, acc in section_accuracy(user, now).items() if acc["total"] >= WEAK_SPOT_MIN_ANSWERS
    ]
    since = (now or timezone.now()) - timedelta(days=WEAK_SPOT_DAYS)
    rows = (
        ExamAnswer.objects.filter(attempt__user=user, answered_at__gte=since, attempt__kind_code=EXAM_KIND_VOCAB)
        .exclude(question_type_code="")
        .values("question_type_code")
        .annotate(n=Count("pk"), ok=Count("pk", filter=Q(is_correct=True)))
        .filter(n__gte=WEAK_SPOT_MIN_ANSWERS)
    )
    spots += [
        {"kind": EXAM_KIND_VOCAB, "code": r["question_type_code"],
         "name": get_code_name(CODE_TYPE_VOCAB_QUESTION, r["question_type_code"]),
         "total": r["n"], "correct": r["ok"], "percent": quiz.percent(r["ok"], r["n"]),
         "level": quiz.score_level(r["ok"], r["n"])}
        for r in rows
    ]
    spots.sort(key=lambda s: (s["percent"], -s["total"]))
    return spots[:WEAK_SPOT_COUNT]


def hub(user):
    return {
        "resume": resume_attempt(user),
        "recent": recent_results(user),
        "weak_spots": weak_spots(user),
        "wrongbook_count": wrongbook.open_count(user),
    }


# =============================================================================
# S2 — Tạo bài từ vựng
# =============================================================================

def scope_counts(user):
    return {
        SCOPE_DUE: attempts.scope_queryset(user, SCOPE_DUE).count(),
        SCOPE_MASTERED: attempts.scope_queryset(user, SCOPE_MASTERED).count(),
    }


def learned_topics(user):
    """Chủ đề có ít nhất VOCAB_MIN_WORDS từ đã học — để chọn ở phạm vi "theo chủ đề".

    Bỏ topic hàng kana (あ行...): chúng chia theo chữ cái đầu, không phải chủ đề học."""
    learned = UserVocabularyProgress.objects.filter(user=user).values("vocabulary_id")
    return list(
        Topic.objects.exclude(slug__endswith=KANA_LINE_SLUG_SUFFIX)
        .annotate(learned=Count("vocabulary_links", filter=Q(vocabulary_links__vocabulary_id__in=learned),
                                distinct=True))
        .filter(learned__gte=VOCAB_MIN_WORDS)
        .order_by("-learned", "name")
    )


# =============================================================================
# Kết quả bài từ vựng
# =============================================================================

def answer_rows(attempt):
    """Các câu của lượt, kèm phương án đã chọn / đáp án để hiển thị lại."""
    rows = []
    for ans in attempt.answers.order_by("order"):
        options = ans.payload.get("options") or []
        correct = ans.payload.get("correct")
        ans.type_name = get_code_name(CODE_TYPE_VOCAB_QUESTION, ans.question_type_code)
        ans.correct_text = options[correct - 1]["text"] if correct and correct <= len(options) else ""
        ans.selected_text = (options[ans.selected - 1]["text"]
                             if ans.selected and ans.selected <= len(options) else "")
        rows.append(ans)
    return rows


def type_breakdown(rows):
    """Đúng / tổng theo dạng câu — bảng nhỏ ở màn kết quả."""
    groups = {}
    for ans in rows:
        g = groups.setdefault(ans.question_type_code, {"name": ans.type_name, "total": 0, "correct": 0})
        g["total"] += 1
        g["correct"] += int(ans.is_correct)
    for g in groups.values():
        g["percent"] = quiz.percent(g["correct"], g["total"])
        g["level"] = quiz.score_level(g["correct"], g["total"])
    return sorted(groups.values(), key=lambda g: g["percent"])


# =============================================================================
# S4 — Chọn đề / luyện dạng đề
# =============================================================================

def exam_set_rows(user):
    """5 bộ đề: số câu theo phần, lượt dở (nếu có), lượt đã xong gần nhất."""
    sets = list(ExamSet.objects.filter(is_active=True).annotate(
        p1=Count("questions", filter=Q(questions__part=1, questions__is_active=True)),
        p2=Count("questions", filter=Q(questions__part=2, questions__is_active=True)),
        p3=Count("questions", filter=Q(questions__part=3, questions__is_active=True)),
    ).order_by("number"))  # GROUP BY bỏ qua Meta.ordering (Django >= 3.1) -> sắp tường minh
    mine = list(ExamAttempt.objects.filter(user=user, kind_code=EXAM_KIND_MOCK, exam_set__in=sets)
                .select_related("exam_set").order_by("-started_at"))
    for exam_set in sets:
        exam_set.open = next((a for a in mine if a.exam_set_id == exam_set.pk and a.finished_at is None), None)
        if exam_set.open is not None:
            exam_set.open.answered = exam_set.open.answers.filter(selected__isnull=False).count()
            decorate(exam_set.open)
        last = next((a for a in mine if a.exam_set_id == exam_set.pk and a.finished_at), None)
        exam_set.last = decorate(last) if last else None
    return sets


def section_rows(user):
    """8 dạng đề cho lưới "Luyện theo dạng đề": số câu, tỷ lệ đúng của người học, dạng yếu nhất."""
    pool = dict(ExamQuestion.objects.filter(is_active=True).values("section_code")
                .annotate(n=Count("pk")).values_list("section_code", "n"))
    acc = section_accuracy(user)
    rows = [{"code": code, "name": section_name(code), "part": int(code[1]), "count": pool.get(code, 0),
             "acc": acc.get(code)} for code in SECTION_ORDER if pool.get(code)]
    scored = [r for r in rows if r["acc"] and r["acc"]["total"] >= WEAK_SPOT_MIN_ANSWERS]
    weakest = min(scored, key=lambda r: r["acc"]["percent"])["code"] if scored else None
    open_ids = dict(ExamAttempt.objects.filter(user=user, kind_code=EXAM_KIND_DRILL, finished_at__isnull=True)
                    .values_list("section_code", "pk"))
    for r in rows:
        r["weakest"] = r["code"] == weakest
        r["open"] = open_ids.get(r["code"])
    return rows


# =============================================================================
# S5 / S6 — làm bài đề thi
# =============================================================================

def exam_options(ans, show_answer):
    """Phương án của câu đề thi, kèm trạng thái ok / ng / off khi được xem đáp án."""
    rows = []
    for opt in ans.question.options.all():
        state = ""
        if show_answer:
            state = "ok" if opt.is_correct else ("ng" if opt.position == ans.selected else "off")
        rows.append({"position": opt.position, "text": opt.text_jp, "state": state,
                     "picked": opt.position == ans.selected})
    return rows


def nav_cells(attempt, answers, current, part):
    """Lưới số câu của phần đang làm: đã trả lời / đang làm / cờ / khoá."""
    cells = []
    for ans in answers:
        if part is not None and ans.question.part != part:
            continue
        cells.append({"order": ans.order,
                      "number": ans.question.number if attempt.kind_code == EXAM_KIND_MOCK else ans.order,
                      "answered": ans.is_answered, "current": ans.order == current.order,
                      "flagged": ans.flagged, "locked": attempts.locked(attempt, ans)})
    return cells


# =============================================================================
# S7 — kết quả đề thi
# =============================================================================

def previous_attempt(attempt):
    """Lượt đã xong ngay trước lượt này, cùng loại và cùng bộ đề / dạng — để so ▲▼."""
    qs = ExamAttempt.objects.filter(user=attempt.user, kind_code=attempt.kind_code, finished_at__isnull=False,
                                    finished_at__lt=attempt.finished_at)
    if attempt.kind_code == EXAM_KIND_MOCK:
        qs = qs.filter(exam_set=attempt.exam_set)
    elif attempt.kind_code == EXAM_KIND_DRILL:
        qs = qs.filter(section_code=attempt.section_code)
    prev = qs.select_related("exam_set").order_by("-finished_at").first()
    return decorate(prev) if prev else None


def exam_review_rows(attempt):
    rows = []
    for ans in attempt.answers.select_related("question").prefetch_related("question__options").order_by("order"):
        q = ans.question
        if q is None:
            continue
        ans.options = exam_options(ans, show_answer=True)
        ans.correct_option = next((o for o in ans.options if o["state"] == "ok"), None)
        ans.selected_option = next((o for o in ans.options if o["picked"]), None)
        ans.section_name = section_name(q.section_code)
        ans.audio_url = exam_audio_url(q)
        rows.append(ans)
    return rows


def exam_breakdown(rows):
    """(theo phần, theo dạng): đúng / tổng / % / thời gian TB mỗi câu."""
    parts, sections = {}, {}
    for ans in rows:
        q = ans.question
        for bucket, key, name in ((parts, q.part, section_name(f"p{q.part}")),
                                  (sections, q.section_code, section_name(q.section_code))):
            g = bucket.setdefault(key, {"key": key, "name": name, "part": q.part, "total": 0, "correct": 0, "ms": 0})
            g["total"] += 1
            g["correct"] += int(ans.is_correct)
            g["ms"] += ans.time_ms
    for g in list(parts.values()) + list(sections.values()):
        g["percent"] = quiz.percent(g["correct"], g["total"])
        g["level"] = quiz.score_level(g["correct"], g["total"])
        g["avg_time"] = format_duration(g["ms"] / 1000 / g["total"]) if g["total"] else ""
    order = {code: i for i, code in enumerate(SECTION_ORDER)}
    return (sorted(parts.values(), key=lambda g: g["key"]),
            sorted(sections.values(), key=lambda g: order.get(g["key"], 99)))


def words_in_wrong(attempt, limit=30):
    """Từ trong kho xuất hiện ở các câu SAI (đề, đoạn văn, đáp án đúng) mà người học
    CHƯA học — gợi ý "thêm vào ôn tập" ở S7. Bỏ từ toàn kana / 1 ký tự (dễ khớp nhầm)."""
    texts = []
    for ans in attempt.answers.filter(is_correct=False).select_related("question").prefetch_related("question__options"):
        q = ans.question
        if q is None:
            continue
        texts += [q.stem_jp, q.passage_jp] + [o.text_jp for o in q.options.all() if o.is_correct]
    blob = "\n".join(t for t in texts if t)
    if not blob:
        return []
    learned = set(UserVocabularyProgress.objects.filter(user=attempt.user).values_list("vocabulary_id", flat=True))
    found = [v for v in Vocabulary.objects.only("pk", "word", "reading", "meaning_vi")
             if v.pk not in learned and len(v.word) >= 2 and not vocab_quiz.is_kana_only(v.word) and v.word in blob]
    # Từ dài trước: 決算報告 đứng trước 決算 / 報告.
    found.sort(key=lambda v: (-len(v.word), v.word))
    return found[:limit]


# =============================================================================
# S8 — Sổ câu sai
# =============================================================================

WRONGBOOK_TABS = ("tat-ca", "tu-vung", "de-thi", "da-ra")
WRONGBOOK_ROW_LIMIT = 200


def wrongbook_overview(user):
    open_qs = wrongbook.open_entries(user)
    return {
        "open": open_qs.count(),
        "half": open_qs.filter(correct_streak__gte=1).count(),
        "cleared": WrongBookEntry.objects.filter(user=user, cleared_at__isnull=False).count(),
        "due_vocab": wrongbook.due_entries(user, wrongbook.TARGET_VOCAB).count(),
        "due_exam": wrongbook.due_entries(user, wrongbook.TARGET_EXAM).count(),
        "counts": {
            "tat-ca": open_qs.count(),
            "tu-vung": open_qs.filter(vocabulary__isnull=False).count(),
            "de-thi": open_qs.filter(question__isnull=False).count(),
            "da-ra": WrongBookEntry.objects.filter(user=user, cleared_at__isnull=False).count(),
        },
    }


def wrongbook_rows(user, tab):
    if tab == "da-ra":
        qs = WrongBookEntry.objects.filter(user=user, cleared_at__isnull=False).order_by("-cleared_at")
    else:
        qs = wrongbook.open_entries(user).order_by("last_wrong_at")
        if tab == "tu-vung":
            qs = qs.filter(vocabulary__isnull=False)
        elif tab == "de-thi":
            qs = qs.filter(question__isnull=False)
    today = user.local_today()
    rows = list(qs.select_related("vocabulary", "question__exam_set")[:WRONGBOOK_ROW_LIMIT])
    for e in rows:
        e.type_name = (get_code_name(CODE_TYPE_VOCAB_QUESTION, e.question_type_code) if e.vocabulary_id
                       else section_name(e.question.section_code))
        e.correct_today = e.last_correct_on == today
    return rows


def wrongbook_cleared_in(attempt):
    """Số mục ra khỏi sổ nhờ lượt ôn này (để màn kết quả nói rõ)."""
    ids = [a.payload.get("wrongbook_entry") for a in attempt.answers.all() if a.payload.get("wrongbook_entry")]
    return WrongBookEntry.objects.filter(pk__in=ids, cleared_at__gte=attempt.started_at).count()
