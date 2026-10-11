"""
Vòng đời một lượt kiểm tra — docs/SPEC_KIEM_TRA.md T7.4, T7.6.

    start_*_attempt  ->  answer (từng câu)  ->  finish
    (quay lại giữa chừng: open_attempt / current_answer)

Ba loại lượt dùng chung bộ máy:
  - vocab : bài từ vựng, câu sinh sẵn (mốc 1)
  - drill : luyện 10 câu một dạng đề — luôn chế độ Luyện
  - mock  : thi thử trọn bộ đề — chế độ Luyện hoặc Thi (◆2)

Chế độ Thi của thi thử (is_timed): làm lần lượt từng phần, mỗi phần bấm giờ; phần Nghe
đi một chiều (trả lời / bỏ qua -> sang câu sau, câu đã qua khoá — vị trí ở scope["cursor"]);
phần Nghe+Đọc và Đọc nhảy câu và đổi đáp án tự do tới khi nộp phần; hết giờ phần tự nộp
(refresh_timing gọi ở đầu mỗi request); câu bỏ trống tính sai; Sổ câu sai ghi lúc nộp bài.

Server bảo đảm: một lượt dở cho mỗi (loại, bộ đề / dạng) — bắt đầu lại = quay về lượt
dở; không chấm một câu hai lần ở chế độ Luyện; chỉ chủ lượt mới đọc/ghi được (views lọc
theo user ngay trong queryset).
"""
import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.constants import (
    EXAM_KIND_DRILL,
    EXAM_KIND_MOCK,
    EXAM_KIND_VOCAB,
    EXAM_MODE_EXAM,
    EXAM_MODE_PRACTICE,
)
from apps.learning.models import UserVocabularyProgress
from apps.vocabulary.models import Vocabulary

from ..constants import (
    DRILL_SIZE,
    SCOPE_DUE,
    SCOPE_MASTERED,
    SCOPE_TOPICS,
    VOCAB_MIN_WORDS,
)
from ..models import ExamAnswer, ExamAttempt, ExamQuestion
from . import hooks, timing, vocab_quiz, wrongbook


@dataclass
class StartResult:
    attempt: ExamAttempt = None
    resumed: bool = False      # đang có lượt dở -> trả lượt đó, không tạo mới
    not_enough: int = None     # không đủ câu / từ: số đang có trong phạm vi


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
# Thi thử / luyện dạng đề (mốc 2 — T7.6)
# =============================================================================

def is_timed(attempt):
    """Chế độ Thi của thi thử: bấm giờ, chia phần, nộp mới thấy đáp án (◆2)."""
    return attempt.kind_code == EXAM_KIND_MOCK and attempt.mode_code == EXAM_MODE_EXAM


def _open_same(user, kind, **filters):
    return ExamAttempt.objects.filter(user=user, kind_code=kind, finished_at__isnull=True, **filters).first()


def start_mock_attempt(user, exam_set, mode):
    """Thi thử trọn một bộ đề. Đang dở bộ này (bất kể chế độ) -> trả lượt đó."""
    existing = _open_same(user, EXAM_KIND_MOCK, exam_set=exam_set)
    if existing is not None:
        return StartResult(attempt=existing, resumed=True)
    questions = list(exam_set.questions.filter(is_active=True).order_by("number"))
    if not questions:
        return StartResult(not_enough=0)
    now = timezone.now()
    with transaction.atomic():
        attempt = ExamAttempt(user=user, kind_code=EXAM_KIND_MOCK, mode_code=mode, exam_set=exam_set,
                              total=len(questions), started_at=now, current_part=questions[0].part,
                              part_started_at={str(questions[0].part): now.isoformat()})
        attempt.save()
        for order, q in enumerate(questions, start=1):
            ExamAnswer(attempt=attempt, order=order, question=q).save()
    return StartResult(attempt=attempt)


def start_drill_attempt(user, section_code, rng=None):
    """Luyện 10 câu một dạng đề (luôn chế độ Luyện). Ưu tiên câu người học CHƯA từng làm."""
    existing = _open_same(user, EXAM_KIND_DRILL, section_code=section_code)
    if existing is not None:
        return StartResult(attempt=existing, resumed=True)
    rng = rng or random.Random()
    pool = list(ExamQuestion.objects.filter(section_code=section_code, is_active=True).values_list("pk", flat=True))
    if not pool:
        return StartResult(not_enough=0)
    done = set(ExamAnswer.objects.filter(attempt__user=user, question_id__in=pool, selected__isnull=False)
               .values_list("question_id", flat=True))
    fresh = [pk for pk in pool if pk not in done]
    seen = [pk for pk in pool if pk in done]
    rng.shuffle(fresh)
    rng.shuffle(seen)
    picked = (fresh + seen)[:DRILL_SIZE]
    with transaction.atomic():
        attempt = ExamAttempt(user=user, kind_code=EXAM_KIND_DRILL, mode_code=EXAM_MODE_PRACTICE,
                              section_code=section_code, total=len(picked), started_at=timezone.now())
        attempt.save()
        for order, pk in enumerate(picked, start=1):
            ExamAnswer(attempt=attempt, order=order, question_id=pk).save()
    return StartResult(attempt=attempt)


def part_answers(attempt, part):
    return list(attempt.answers.select_related("question").filter(question__part=part).order_by("order"))


def parts_of(attempt):
    return sorted({p for p in attempt.answers.values_list("question__part", flat=True) if p})


def cursor(attempt):
    """Câu đang làm của phần Nghe (chế độ Thi) — câu có order nhỏ hơn đã bị khoá."""
    return attempt.scope.get("cursor")


def _set_cursor(attempt, order):
    attempt.scope = {**attempt.scope, "cursor": order}


def submit_part(attempt, now=None):
    """Nộp phần hiện tại (chế độ Thi). Còn phần sau -> mở phần sau; hết -> nộp bài."""
    if not is_timed(attempt) or attempt.is_finished:
        return
    now = now or timezone.now()
    part = attempt.current_part
    attempt.part_submitted_at = {**attempt.part_submitted_at, str(part): now.isoformat()}
    later = [p for p in parts_of(attempt) if p > part]
    if later:
        attempt.current_part = later[0]
        attempt.part_started_at = {**attempt.part_started_at, str(later[0]): now.isoformat()}
        _set_cursor(attempt, None)
        attempt.save()
    else:
        attempt.save()
        finish(attempt, force=True)


def refresh_timing(attempt, now=None):
    """Gọi ở đầu mỗi request: phần đã quá hạn thì tự nộp (kể cả khi trình duyệt tắt JS)."""
    while is_timed(attempt) and not attempt.is_finished and timing.is_part_closed(attempt, attempt.current_part, now):
        submit_part(attempt, now)


def _advance_listening(attempt, answers, order):
    after = [a.order for a in answers if a.order > order]
    if after:
        _set_cursor(attempt, after[0])
        attempt.save(update_fields=["scope", "updated_at", "updated_by"])
    else:
        submit_part(attempt)


def skip(attempt, order):
    """Phần Nghe chế độ Thi: bỏ qua câu đang làm -> sang câu sau (câu bỏ qua bị khoá, tính sai)."""
    if not is_timed(attempt) or attempt.current_part != timing.LISTENING_PART:
        return
    answers = part_answers(attempt, timing.LISTENING_PART)
    current = cursor(attempt) or (answers[0].order if answers else None)
    if order != current:
        return
    _advance_listening(attempt, answers, order)


def toggle_flag(attempt, order):
    ExamAnswer.objects.filter(attempt=attempt, order=order).update(flagged=~F("flagged"))


def locked(attempt, ans):
    """Câu không làm / không đổi được nữa (chế độ Thi)."""
    if not is_timed(attempt) or ans.question_id is None:
        return False
    if ans.question.part != attempt.current_part:
        return True
    if ans.question.part == timing.LISTENING_PART:
        current = cursor(attempt)
        if current is None:
            first = part_answers(attempt, timing.LISTENING_PART)
            current = first[0].order if first else None
        return ans.order != current
    return timing.is_part_closed(attempt, ans.question.part)


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
    """Chấm câu `order`.

    - Bài từ vựng, luyện dạng đề, thi thử chế độ Luyện: câu đã trả lời giữ nguyên lần đầu.
    - Thi thử chế độ Thi: phần Đọc / Nghe+Đọc đổi được đáp án tới khi nộp phần; phần Nghe
      trả lời là sang câu sau, câu đã qua khoá. Không chấm phần đã đóng.
    Trả về AnswerResult, hoặc None nếu không chấm được (đã nộp, khoá, lựa chọn sai phạm vi).
    """
    if attempt.is_finished:
        return None
    timed = is_timed(attempt)
    with transaction.atomic():
        # of=("self",): chỉ khoá dòng ExamAnswer — PostgreSQL không cho FOR UPDATE
        # lên phía nullable của LEFT JOIN (question rỗng với câu từ vựng).
        ans = (ExamAnswer.objects.select_for_update(of=("self",)).select_related("question")
               .filter(attempt=attempt, order=order).first())
        if ans is None or not (1 <= int(selected) <= option_count(ans)):
            return None
        if timed and locked(attempt, ans):
            return None
        if ans.is_answered and not timed:
            return AnswerResult(answer=ans, first_time=False)
        first = not ans.is_answered
        ans.selected = int(selected)
        ans.is_correct = _is_correct(ans, ans.selected)
        ans.answered_at = timezone.now()
        ans.time_ms = max(0, min(int(time_ms or 0), 3_600_000)) + (0 if first else ans.time_ms)
        ans.save()
        # Đếm lại thay vì +1: hai request song song vẫn ra đúng điểm.
        attempt.score = attempt.answers.filter(is_correct=True).count()
        attempt.save(update_fields=["score", "updated_at", "updated_by"])

    if timed:
        # Chế độ Thi: không phản hồi, không ghi sổ ngay (ghi lúc nộp bài — spec T7.8).
        if ans.question.part == timing.LISTENING_PART:
            _advance_listening(attempt, part_answers(attempt, timing.LISTENING_PART), order)
        return AnswerResult(answer=ans, first_time=first)

    effect = hooks.on_vocab_answer(attempt, ans)
    if not ans.is_correct:
        wrongbook.record_wrong(
            attempt.user, question=ans.question if ans.question_id else None,
            vocabulary=ans.vocabulary if not ans.question_id else None,
            question_type_code="" if ans.question_id else ans.question_type_code,
        )
    return AnswerResult(answer=ans, first_time=True, srs_effect=effect)


def finish(attempt, force=False):
    """Nộp bài. Bài từ vựng / luyện còn câu chưa làm -> False (phải làm hết).

    Thi thử chế độ Thi luôn nộp được (hết giờ, nộp sớm): câu bỏ trống tính sai, và mọi câu
    sai / bỏ trống được ghi Sổ câu sai lúc này.
    """
    if attempt.is_finished:
        return True
    if not force and not is_timed(attempt) and attempt.answers.filter(selected__isnull=True).exists():
        return False
    attempt.score = attempt.answers.filter(is_correct=True).count()
    attempt.total = attempt.answers.count()
    attempt.finished_at = timezone.now()
    attempt.save()
    if is_timed(attempt):
        for ans in attempt.answers.filter(is_correct=False).select_related("question"):
            wrongbook.record_wrong(attempt.user, question=ans.question)
    hooks.on_finish(attempt)
    return True


def abandon(attempt):
    """Bỏ lượt dở. Lịch ôn đã cập nhật theo các câu đã làm thì giữ nguyên."""
    if attempt.is_finished:
        return False
    attempt.delete()
    return True
