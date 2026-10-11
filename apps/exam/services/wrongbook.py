"""
Sổ câu sai — docs/SPEC_KIEM_TRA.md T7.8.

Ghi sổ: mọi câu sai ở bài từ vựng / luyện dạng đề / thi thử chế độ Luyện (ngay khi
trả lời) và thi thử chế độ Thi (lúc nộp bài) -> record_wrong.

Ôn sổ (lượt kind "wrongbook", mỗi lượt một loại: từ vựng HOẶC đề thi): mỗi câu trong
lượt mang id mục sổ (payload["wrongbook_entry"]) để cập nhật đúng mục kể cả khi câu
từ vựng phải đổi dạng -> mark_right / mark_wrong.

◆4: một mục ra khỏi sổ khi đúng WRONGBOOK_CLEAR_STREAK lần liên tiếp, mỗi lần một NGÀY
khác nhau (ngày theo múi giờ người học). Sai lại thì về 0 và quay lại sổ.
"""
from django.utils import timezone

from ..constants import WRONGBOOK_CLEAR_STREAK
from ..models import WrongBookEntry

TARGET_VOCAB = "tu-vung"
TARGET_EXAM = "de-thi"
TARGETS = (TARGET_VOCAB, TARGET_EXAM)


def _target(question=None, vocabulary=None, question_type_code=""):
    if question is not None:
        return {"question": question}
    return {"vocabulary": vocabulary, "question_type_code": question_type_code}


def record_wrong(user, *, question=None, vocabulary=None, question_type_code="", now=None):
    now = now or timezone.now()
    entry, created = WrongBookEntry.objects.get_or_create(
        user=user, **_target(question, vocabulary, question_type_code),
        defaults={"last_wrong_at": now},
    )
    if not created:
        mark_wrong(entry, now)
    return entry


def mark_wrong(entry, now=None):
    entry.wrong_count += 1
    entry.correct_streak = 0
    entry.last_wrong_at = now or timezone.now()
    entry.cleared_at = None
    entry.save()
    return entry


def mark_right(entry, now=None):
    """Một lần đúng khi ôn sổ. Đúng lần nữa trong CÙNG ngày không tính (◆4)."""
    if entry.cleared_at is not None:
        return entry
    today = entry.user.local_today()
    if entry.last_correct_on == today:
        return entry
    entry.correct_streak += 1
    entry.last_correct_on = today
    if entry.correct_streak >= WRONGBOOK_CLEAR_STREAK:
        entry.cleared_at = now or timezone.now()
    entry.save()
    return entry


def record_right(user, *, question=None, vocabulary=None, question_type_code="", now=None):
    """Như mark_right nhưng tìm mục theo đích. Không có mục còn trong sổ -> None."""
    entry = WrongBookEntry.objects.filter(
        user=user, cleared_at__isnull=True, **_target(question, vocabulary, question_type_code),
    ).first()
    return mark_right(entry, now) if entry else None


def open_entries(user):
    return WrongBookEntry.objects.filter(user=user, cleared_at__isnull=True)


def due_entries(user, target=None):
    """Mục ôn được hôm nay: còn trong sổ và hôm nay CHƯA trả lời đúng (đúng lần 2 phải khác ngày)."""
    qs = open_entries(user).exclude(last_correct_on=user.local_today())
    if target == TARGET_VOCAB:
        qs = qs.filter(vocabulary__isnull=False)
    elif target == TARGET_EXAM:
        qs = qs.filter(question__isnull=False, question__is_active=True)
    return qs.order_by("last_wrong_at", "pk")


def open_count(user):
    return open_entries(user).count()
