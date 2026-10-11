"""
Truy vấn chỉ đọc của khu Kiểm tra — S1 Tổng quan, S2 Tạo bài, kết quả bài từ vựng.
Ghi dữ liệu nằm ở apps/exam/services/.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.core import quiz
from apps.core.constants import (
    CODE_TYPE_EXAM_KIND,
    CODE_TYPE_VOCAB_QUESTION,
    EXAM_KIND_VOCAB,
)
from apps.core.mastercode import get_code_name
from apps.learning.models import UserVocabularyProgress
from apps.vocabulary.models import Topic

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
from .models import ExamAnswer, ExamAttempt
from .services import attempts, wrongbook


def decorate(attempt):
    """Gắn số liệu hiển thị cho một lượt: %, mức màu, tên loại."""
    attempt.percent = quiz.percent(attempt.score, attempt.total)
    attempt.level = quiz.score_level(attempt.score, attempt.total)
    attempt.kind_name = get_code_name(CODE_TYPE_EXAM_KIND, attempt.kind_code)
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
    rows = ExamAttempt.objects.filter(user=user, finished_at__isnull=False).order_by("-finished_at")[:limit]
    return [decorate(a) for a in rows]


def weak_spots(user, now=None):
    """Dạng câu từ vựng đúng thấp nhất trong 30 ngày (mỗi dạng cần >= 5 câu).

    Mốc 2 thêm dạng đề BJT (theo ExamQuestion.section_code)."""
    since = (now or timezone.now()) - timedelta(days=WEAK_SPOT_DAYS)
    rows = (
        ExamAnswer.objects.filter(attempt__user=user, answered_at__gte=since, attempt__kind_code=EXAM_KIND_VOCAB)
        .exclude(question_type_code="")
        .values("question_type_code")
        .annotate(n=Count("pk"), ok=Count("pk", filter=Q(is_correct=True)))
        .filter(n__gte=WEAK_SPOT_MIN_ANSWERS)
    )
    spots = [
        {"code": r["question_type_code"],
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
