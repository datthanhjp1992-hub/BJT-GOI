"""
Bộ lọc từ vựng dùng CHUNG cho hai nơi:

* SC05 (`apps.vocabulary.views`) — dựng bảng kết quả.
* Phiên học bắt đầu từ SC05 (`apps.learning.views.study_start_view`) — dựng
  hàng đợi flashcard.

Hai nơi PHẢI cho ra cùng một tập từ, nếu không người học sẽ thấy bảng một
đằng còn học một nẻo. Vì vậy mọi logic lọc nằm ở đây, không viết lại ở view.
"""
from datetime import timedelta

from django.db.models import Exists, F, OuterRef, Q

from apps.core.utils import TOPIC_PARAM
from apps.learning.models import UserVocabularyProgress

from .models import Topic, Vocabulary

# --- Tên tham số trên query string / form -----------------------------------
SEARCH_PARAM = "q"
STATUS_PARAM = "status"
LIMIT_PARAM = "limit"
# Cờ đánh dấu "người dùng đã bấm Lọc". Vào trang trần (không có cờ, không có
# tham số lọc nào) thì view KHÔNG đụng vào DB — xem `is_filter_request()`.
FILTERED_PARAM = "filtered"

# --- Trạng thái học ---------------------------------------------------------
STATUS_NEW = "new"
STATUS_LEARNING = "learning"
STATUS_MASTERED = "mastered"
STATUS_CODES = (STATUS_NEW, STATUS_LEARNING, STATUS_MASTERED)
STATUS_LABEL_KEYS = {
    STATUS_NEW: "vocabulary.list.tag.status.new",
    STATUS_LEARNING: "vocabulary.list.tag.status.learning",
    STATUS_MASTERED: "vocabulary.list.tag.status.mastered",
}

# Trần kết quả cho nhánh tìm kiếm. `VocabularyQuerySet.search()` sắp xếp theo
# điểm trigram nên PHẢI cắt ở tầng SQL (nếu không Postgres phải chấm điểm cả
# bảng); 200 là quá đủ cho người học lướt xem, quá số này thì gõ từ khoá rõ hơn.
SEARCH_LIMIT = 200

# --- Số từ tối đa cho MỘT phiên học ----------------------------------------
# 0 = không giới hạn. Mặc định 20 để một lượt học không kéo dài vô tận khi
# người dùng lọc cả nghìn từ.
SESSION_LIMIT_CHOICES = (10, 20, 50, 100, 0)
DEFAULT_SESSION_LIMIT = 20


def is_filter_request(data, forced=False):
    """Người dùng đã thực sự yêu cầu dữ liệu chưa?

    `forced` dành cho route /vocabulary/topic/<slug>/ — link đó tự nó đã là
    một bộ lọc. Ngoài ra chỉ cần có MỘT tham số lọc bất kỳ (kể cả `page` của
    link phân trang) là coi như đã lọc, để link cũ/bookmark không gãy.
    """
    if forced:
        return True
    keys = (FILTERED_PARAM, TOPIC_PARAM, SEARCH_PARAM, STATUS_PARAM, "page")
    return any(data.get(key) for key in keys)


def clean_statuses(values):
    """Bỏ mã lạ, bỏ trùng, giữ thứ tự khai báo ở STATUS_CODES."""
    picked = {v for v in values if v in STATUS_CODES}
    return [code for code in STATUS_CODES if code in picked]


def clean_session_limit(raw):
    """Số từ tối đa mỗi phiên — giá trị lạ thì rơi về mặc định."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_SESSION_LIMIT
    return value if value in SESSION_LIMIT_CHOICES else DEFAULT_SESSION_LIMIT


def selected_topics(data, forced_slug=None):
    """Danh sách Topic đang chọn, theo đúng thứ tự xuất hiện trên request.

    Slug không tồn tại bị LỜ ĐI (không 404): người dùng sửa URL bằng tay
    không đáng phải nhận trang lỗi.
    """
    slugs = list(data.getlist(TOPIC_PARAM))
    if forced_slug:
        slugs.insert(0, forced_slug)
    if not slugs:
        return []

    by_slug = {t.slug: t for t in Topic.objects.filter(slug__in=slugs)}
    result, seen = [], set()
    for slug in slugs:
        if slug in by_slug and slug not in seen:
            seen.add(slug)
            result.append(by_slug[slug])
    return result


def annotate_progress(words, user):
    """Gắn 2 cờ EXISTS để lọc theo trạng thái mà KHÔNG join nhân bản dòng.

    Dùng subquery thay vì `filter(progress__user=...)` vì nhánh "Chưa học" là
    một phủ định — viết bằng join sẽ ra kết quả sai khi từ có tiến độ của
    người dùng khác.
    """
    progress = UserVocabularyProgress.objects.filter(user=user, vocabulary=OuterRef("pk"))
    return words.annotate(
        has_progress=Exists(progress),
        has_mastered=Exists(progress.filter(is_mastered=True)),
    )


def filter_vocabulary(user, topics=(), query="", statuses=(), search_limit=SEARCH_LIMIT):
    """Queryset từ vựng khớp bộ lọc của SC05.

    Thứ tự BẮT BUỘC: chủ đề -> trạng thái -> tìm kiếm. `.search()` trả về
    queryset ĐÃ cắt (slice) nên mọi filter phải đứng trước nó.
    """
    words = Vocabulary.objects.prefetch_related("topics")

    topics = list(topics)
    if topics:
        # HOẶC: từ chỉ cần thuộc một trong các chủ đề đã chọn. `distinct()` vì
        # join M2M nhân bản dòng khi một từ khớp nhiều chủ đề đang chọn.
        words = words.filter(topics__in=topics).distinct()

    statuses = clean_statuses(statuses)
    # Tích cả 3 trạng thái = không lọc gì cả, khỏi tốn 2 subquery.
    if statuses and len(statuses) < len(STATUS_CODES):
        words = annotate_progress(words, user)
        condition = Q()
        if STATUS_NEW in statuses:
            condition |= Q(has_progress=False)
        if STATUS_LEARNING in statuses:
            condition |= Q(has_progress=True, has_mastered=False)
        if STATUS_MASTERED in statuses:
            condition |= Q(has_mastered=True)
        words = words.filter(condition)

    query = (query or "").strip()
    if query:
        return words.search(query, limit=search_limit)
    return words.order_by("word")


# =============================================================================
# SC15 — Ôn tập: chỉ những từ NGƯỜI DÙNG ĐÃ HỌC
# -----------------------------------------------------------------------------
# Khác hẳn `filter_vocabulary()` ở trên (SC05 duyệt CẢ KHO từ, kể cả từ chưa
# học): ở đây điều kiện bắt buộc là từ phải có một dòng
# `UserVocabularyProgress` của chính user. Vì vậy hàm nằm riêng thay vì thêm
# một cờ nữa vào filter_vocabulary — hai màn hỏi hai câu hỏi khác nhau.
# =============================================================================

REVIEW_SCOPE_PARAM = "scope"

SCOPE_DUE = "due"              # quá hạn + đến hạn hôm nay
SCOPE_LEECH = "leech"          # hay sai (sai nhiều hơn đúng)
SCOPE_UPCOMING = "upcoming"    # sẽ đến hạn trong N ngày tới (CHƯA đến hạn)
SCOPE_MASTERED = "mastered"    # đã thuộc
REVIEW_SCOPES = (SCOPE_DUE, SCOPE_LEECH, SCOPE_UPCOMING, SCOPE_MASTERED)

# Số ngày của nhóm "sắp đến hạn".
UPCOMING_DAYS = 7

# Sai 1 lần chưa đủ để gọi là "hay quên" — ngưỡng này lọc bớt nhiễu.
LEECH_MIN_WRONG = 2

# Hai phạm vi này là ÔN THÊM ngoài lịch: người học chủ động ôn sớm những từ
# chưa đến hạn. Ôn chúng KHÔNG được đẩy `next_review_date` (xem
# `apps.learning.services.record_extra_review` và ghi chú ở
# `apps.learning.views.review_start_view`) — nếu đẩy, ôn 3 lượt trong một tối
# sẽ thổi `interval_days` lên vô lý và từ đó biến mất khỏi lịch ôn thật.
SCOPES_WITHOUT_SCHEDULE = (SCOPE_UPCOMING, SCOPE_MASTERED)


def clean_review_scope(raw):
    """Mã phạm vi lạ (người dùng sửa URL/form bằng tay) rơi về "đến hạn"."""
    return raw if raw in REVIEW_SCOPES else SCOPE_DUE


def touches_schedule(scope):
    """Ôn theo phạm vi này có được cập nhật lịch SM-2 không?"""
    return clean_review_scope(scope) not in SCOPES_WITHOUT_SCHEDULE


def progress_filter_for_scope(user, scope):
    """Điều kiện lọc trên `UserVocabularyProgress` ứng với một phạm vi ôn.

    Trả về một `Q` để cả `studied_vocabulary()` (dựng hàng đợi) và
    `apps.learning.services.get_review_overview()` (đếm số) dùng CHUNG một
    định nghĩa — nếu hai nơi tự viết điều kiện riêng thì con số trên thẻ và
    số từ thật sự ôn được sẽ lệch nhau mà không ai nhận ra.
    """
    today = user.local_today()
    scope = clean_review_scope(scope)
    if scope == SCOPE_LEECH:
        return Q(wrong_count__gt=F("correct_count"), wrong_count__gte=LEECH_MIN_WRONG)
    if scope == SCOPE_UPCOMING:
        return Q(
            next_review_date__gt=today,
            next_review_date__lte=today + timedelta(days=UPCOMING_DAYS),
        )
    if scope == SCOPE_MASTERED:
        return Q(is_mastered=True)
    # SCOPE_DUE: `next_review_date` null nghĩa là có tiến độ nhưng chưa được
    # xếp lịch — coi như đến hạn ngay, giống `build_study_queue()`.
    return Q(next_review_date__lte=today) | Q(next_review_date__isnull=True)


def studied_vocabulary(user, topics=(), scope=SCOPE_DUE):
    """Từ ĐÃ HỌC của `user` khớp phạm vi ôn, sắp theo hạn ôn gần nhất trước.

    Trả về queryset `Vocabulary` (không phải `UserVocabularyProgress`) để
    `apps.learning.services.build_study_queue()` dùng lại được nguyên vẹn.
    """
    progress = UserVocabularyProgress.objects.filter(
        user=user, vocabulary=OuterRef("pk")
    ).filter(progress_filter_for_scope(user, scope))

    words = Vocabulary.objects.prefetch_related("topics").filter(Exists(progress))
    topics = list(topics)
    if topics:
        words = words.filter(topics__in=topics).distinct()
    return words.order_by("word")
