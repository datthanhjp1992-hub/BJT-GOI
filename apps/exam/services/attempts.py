"""
Vòng đời một lượt kiểm tra — docs/SPEC_KIEM_TRA.md T7.4.

    start_vocab_attempt  ->  answer (từng câu)  ->  finish
    (quay lại giữa chừng: open_attempt / current_answer)

Server bảo đảm: một người chỉ có MỘT lượt dở cho mỗi loại bài từ vựng (bắt
đầu lại = quay về lượt dở), không chấm một câu hai lần (F5, bấm hai lần), chỉ
chủ lượt mới đọc/ghi được lượt (lọc theo user ngay trong queryset ở views).
"""
import random
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.core.constants import EXAM_KIND_VOCAB, EXAM_MODE_PRACTICE
from apps.learning.models import UserVocabularyProgress
from apps.vocabulary.models import Vocabulary

from ..constants import (
    SCOPE_DUE,
    SCOPE_MASTERED,
    SCOPE_TOPICS,
    VOCAB_MIN_WORDS,
)
from ..models import ExamAnswer, ExamAttempt
from . import hooks, vocab_quiz, wrongbook


@dataclass
class StartResult:
    attempt: ExamAttempt = None
    resumed: bool = False      # đang có lượt dở -> trả lượt đó, không tạo mới
    not_enough: int = None     # không đủ từ: số từ đang có trong phạm vi


@dataclass
class AnswerResult:
    answer: ExamAnswer
    first_time: bool           # False = câu đã trả lời từ trước, không chấm lại
    srs_effect: str = None     # "relearn" / "reviewed" / None — xem hooks.on_vocab_answer


# =============================================================================
# Phạm vi bài từ vựng
# =============================================================================

def scope_queryset(user, scope, topic_ids=()):
    """Từ thuộc phạm vi — luôn chỉ là từ ĐÃ HỌC (có dòng tiến độ)."""
    progress = UserVocabularyProgress.objects.filter(user=user)
    if scope == SCOPE_DUE:
        progress = progress.filter(hooks.due_q(user))
    elif scope == SCOPE_MASTERED:
        progress = progress.filter(is_mastered=True)
    elif scope == SCOPE_TOPICS:
        progress = progress.filter(vocabulary__topics__in=list(topic_ids))
    else:
        return Vocabulary.objects.none()
    return Vocabulary.objects.filter(pk__in=progress.values("vocabulary_id")).distinct()


def open_attempt(user, kind=None):
    qs = ExamAttempt.objects.filter(user=user, finished_at__isnull=True)
    if kind:
        qs = qs.filter(kind_code=kind)
    return qs.order_by("-started_at").first()


def start_vocab_attempt(user, *, scope, topic_ids=(), types=(), count=20, srs_link=True, rng=None):
    existing = open_attempt(user, EXAM_KIND_VOCAB)
    if existing is not None:
        return StartResult(attempt=existing, resumed=True)

    pool = scope_queryset(user, scope, topic_ids)
    pool_ids = list(pool.values_list("pk", flat=True))
    if len(pool_ids) < VOCAB_MIN_WORDS:
        return StartResult(not_enough=len(pool_ids))

    rng = rng or random.Random()
    chosen_ids = rng.sample(pool_ids, k=min(count, len(pool_ids)))
    words = vocab_quiz.candidate_words(Vocabulary.objects.filter(pk__in=chosen_ids))
    questions = vocab_quiz.build(words, types, rng)

    with transaction.atomic():
        attempt = ExamAttempt(
            user=user,
            kind_code=EXAM_KIND_VOCAB,
            mode_code=EXAM_MODE_PRACTICE,
            scope={"scope": scope, "topic_ids": [int(t) for t in topic_ids],
                   "types": list(types), "srs_link": bool(srs_link)},
            total=len(questions),
            started_at=timezone.now(),
        )
        attempt.save()
        for order, (vocab, qtype, payload) in enumerate(questions, start=1):
            ExamAnswer(attempt=attempt, order=order, vocabulary=vocab,
                       question_type_code=qtype, payload=payload).save()
    return StartResult(attempt=attempt)


# =============================================================================
# Làm bài
# =============================================================================

def current_answer(attempt):
    """Câu chưa trả lời đầu tiên, None nếu đã làm hết."""
    return attempt.answers.filter(selected__isnull=True).order_by("order").first()


def _is_correct(answer, selected):
    if answer.question_id:
        return answer.question.options.filter(position=selected, is_correct=True).exists()
    return selected == answer.payload.get("correct")


def option_count(answer):
    if answer.question_id:
        return answer.question.options.count()
    return len(answer.payload.get("options") or [])


def answer(attempt, order, selected, time_ms=0):
    """Chấm câu `order`. Câu đã trả lời thì giữ nguyên lần đầu (chế độ Luyện / bài từ vựng).

    Trả về AnswerResult, hoặc None nếu lượt đã nộp / câu không tồn tại / lựa chọn ngoài phạm vi.
    """
    if attempt.is_finished:
        return None
    with transaction.atomic():
        # of=("self",): chỉ khoá dòng ExamAnswer — PostgreSQL không cho FOR UPDATE
        # lên phía nullable của LEFT JOIN (question rỗng với câu từ vựng).
        ans = (ExamAnswer.objects.select_for_update(of=("self",)).select_related("question")
               .filter(attempt=attempt, order=order).first())
        if ans is None or not (1 <= int(selected) <= option_count(ans)):
            return None
        if ans.is_answered:
            return AnswerResult(answer=ans, first_time=False)
        ans.selected = int(selected)
        ans.is_correct = _is_correct(ans, ans.selected)
        ans.answered_at = timezone.now()
        ans.time_ms = max(0, min(int(time_ms or 0), 3_600_000))
        ans.save()
        # Đếm lại thay vì +1: hai request song song vẫn ra đúng điểm.
        attempt.score = attempt.answers.filter(is_correct=True).count()
        attempt.save(update_fields=["score", "updated_at", "updated_by"])

    effect = hooks.on_vocab_answer(attempt, ans)
    if not ans.is_correct:
        wrongbook.record_wrong(
            attempt.user, question=ans.question if ans.question_id else None,
            vocabulary=ans.vocabulary if not ans.question_id else None,
            question_type_code="" if ans.question_id else ans.question_type_code,
        )
    return AnswerResult(answer=ans, first_time=True, srs_effect=effect)


def finish(attempt):
    """Nộp bài. Trả về False nếu còn câu chưa làm (bài từ vựng phải làm hết)."""
    if attempt.is_finished:
        return True
    if attempt.answers.filter(selected__isnull=True).exists():
        return False
    attempt.score = attempt.answers.filter(is_correct=True).count()
    attempt.total = attempt.answers.count()
    attempt.finished_at = timezone.now()
    attempt.save()
    hooks.on_finish(attempt)
    return True


def abandon(attempt):
    """Bỏ lượt dở. Lịch ôn đã cập nhật theo các câu đã làm thì giữ nguyên."""
    if attempt.is_finished:
        return False
    attempt.delete()
    return True
