"""
Sổ câu sai — docs/SPEC_KIEM_TRA.md T7.8.

Mốc 1 chỉ GHI sổ (câu sai ở bài từ vựng); màn S8 và lượt ôn sổ làm ở mốc 3,
nhưng ghi ngay từ bây giờ để lúc mở S8 đã có sẵn dữ liệu thật.

◆4: một mục ra khỏi sổ khi đúng WRONGBOOK_CLEAR_STREAK lần liên tiếp, mỗi lần
một NGÀY khác nhau (ngày theo múi giờ người học). Sai lại thì về 0 và quay lại sổ.
"""
from django.utils import timezone

from ..constants import WRONGBOOK_CLEAR_STREAK
from ..models import WrongBookEntry


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
        entry.wrong_count += 1
        entry.correct_streak = 0
        entry.last_wrong_at = now
        entry.cleared_at = None
        entry.save()
    return entry


def record_right(user, *, question=None, vocabulary=None, question_type_code="", now=None):
    """Câu đúng ở lượt ÔN SỔ. Không có mục trong sổ -> không làm gì, trả None."""
    entry = WrongBookEntry.objects.filter(
        user=user, cleared_at__isnull=True, **_target(question, vocabulary, question_type_code),
    ).first()
    if entry is None:
        return None
    today = user.local_today()
    if entry.last_correct_on == today:
        return entry  # đúng lần 2 trong cùng ngày không tính (◆4)
    entry.correct_streak += 1
    entry.last_correct_on = today
    if entry.correct_streak >= WRONGBOOK_CLEAR_STREAK:
        entry.cleared_at = now or timezone.now()
    entry.save()
    return entry


def open_count(user):
    return WrongBookEntry.objects.filter(user=user, cleared_at__isnull=True).count()
