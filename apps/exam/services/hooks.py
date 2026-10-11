"""
Nối khu Kiểm tra sang app khác — SRS (apps.learning) và streak/danh hiệu.

◆1 (Dat duyệt 11/10/2026) khi scope["srs_link"] bật:
  - câu SAI   -> review_word(AGAIN): từ về "học lại", quay lại ở phiên học kế;
  - câu ĐÚNG + phạm vi "từ đến hạn" + từ đang nợ ôn -> review_word(GOOD),
    tức bài kiểm tra thay cho lượt ôn flashcard của từ đó;
  - còn lại không đụng lịch ôn.
Gọi NGAY khi trả lời (không đợi nộp bài) để thoát giữa chừng vẫn tính.

Nộp bài -> ghi một learning.StudySession kiểu "quiz", như bài tập kính ngữ ghi
kiểu "keigo": streak, biểu đồ lịch sử và danh hiệu "Kiểm tra" (đếm phiên quiz
>= 80%, apps/gamification/services.py) tự tính, không phải sửa app khác.
"""
from django.db.models import Q

from apps.core.constants import EXAM_KIND_VOCAB, SESSION_TYPE_QUIZ
from apps.learning import services as learning
from apps.learning import srs
from apps.learning.models import StudySession, UserVocabularyProgress

from ..constants import SCOPE_DUE


def due_q(user):
    """Từ đang NỢ ÔN hôm nay — đúng định nghĩa learning.services.count_backlog():
    từ ôn đến hạn/quá hạn + từ dở bước học. Không lấy từ đang học trong ngày
    (bước 1-10 phút) vì chúng chưa tới lượt ôn."""
    today = user.local_today()
    return (
        Q(card_state=srs.REVIEW, next_review_date__lte=today)
        | Q(card_state=srs.REVIEW, next_review_date__isnull=True)
        | learning.leftover_learning_q(user)
    )


def is_due(progress):
    return UserVocabularyProgress.objects.filter(pk=progress.pk).filter(due_q(progress.user)).exists()


def on_vocab_answer(attempt, answer):
    """Trả về "relearn" / "reviewed" / None — để màn phản hồi nói đúng việc đã làm."""
    if attempt.kind_code != EXAM_KIND_VOCAB or not attempt.scope.get("srs_link"):
        return None
    if answer.vocabulary_id is None:
        return None
    progress = UserVocabularyProgress.objects.filter(user=attempt.user, vocabulary_id=answer.vocabulary_id).first()
    if progress is None:  # bài từ vựng chỉ lấy từ đã học, nhưng từ có thể bị xoá tiến độ giữa chừng
        return None
    if not answer.is_correct:
        learning.review_word(progress, srs.AGAIN)
        return "relearn"
    if attempt.scope.get("scope") == SCOPE_DUE and is_due(progress):
        learning.review_word(progress, srs.GOOD)
        return "reviewed"
    return None


def on_finish(attempt):
    """Ghi StudySession kiểu quiz cho lượt vừa nộp (bỏ qua lượt ôn sổ câu sai)."""
    StudySession.objects.create(
        user=attempt.user,
        session_type=SESSION_TYPE_QUIZ,
        words_reviewed=attempt.total,
        correct_answers=attempt.score,
        started_at=attempt.started_at,
        ended_at=attempt.finished_at,
    )
