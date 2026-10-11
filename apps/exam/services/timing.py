"""
Hạn giờ và khoá câu ở chế độ Thi — docs/SPEC_KIEM_TRA.md T7.4, ◆2.

Hạn KHÔNG lưu cứng: hạn phần = part_started_at[part] + PART_MINUTES[part], tính
lúc cần, nên đổi thời lượng không phải sửa dữ liệu. Server là nơi quyết định
(trình duyệt chỉ hiển thị số giây còn lại server trả về).

"Audio phát 1 lần" KHÔNG chặn được ở đây — file audio là URL công khai, chỉ
trình duyệt khoá nút phát. Chấp nhận (spec mục 4).
"""
from datetime import datetime, timedelta

from django.utils import timezone

from apps.core.constants import EXAM_MODE_EXAM

from ..constants import PART_MINUTES

LISTENING_PART = 1


def _parse(value):
    return datetime.fromisoformat(value) if value else None


def part_deadline(attempt, part):
    """Hạn nộp của phần `part`, None nếu không bấm giờ hoặc phần chưa bắt đầu."""
    if attempt.mode_code != EXAM_MODE_EXAM or part not in PART_MINUTES:
        return None
    started = _parse(attempt.part_started_at.get(str(part)))
    if started is None:
        return None
    return started + timedelta(minutes=PART_MINUTES[part])


def seconds_left(attempt, part, now=None):
    deadline = part_deadline(attempt, part)
    if deadline is None:
        return None
    return max(0, int((deadline - (now or timezone.now())).total_seconds()))


def is_part_closed(attempt, part, now=None):
    """Phần đã nộp, hoặc đã quá hạn (chế độ Thi)."""
    if str(part) in attempt.part_submitted_at:
        return True
    left = seconds_left(attempt, part, now)
    return left is not None and left == 0


def is_locked(attempt, answer, current_order, now=None):
    """Câu `answer` có bị khoá không (không xem lại / không trả lời được)?

    - Phần đã đóng: khoá cả phần.
    - Chế độ Thi, phần Nghe: câu ĐÃ QUA (order nhỏ hơn câu hiện tại) bị khoá.
    """
    part = answer.question.part if answer.question_id else None
    if part is None or attempt.mode_code != EXAM_MODE_EXAM:
        return False
    if is_part_closed(attempt, part, now):
        return True
    return part == LISTENING_PART and current_order is not None and answer.order < current_order
