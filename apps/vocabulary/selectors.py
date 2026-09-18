"""
Bộ lọc từ vựng dùng CHUNG cho hai nơi:

* SC05 (`apps.vocabulary.views`) — dựng bảng kết quả.
* Phiên học bắt đầu từ SC05 (`apps.learning.views.study_start_view`) — dựng
  hàng đợi flashcard.

Hai nơi PHẢI cho ra cùng một tập từ, nếu không người học sẽ thấy bảng một
đằng còn học một nẻo. Vì vậy mọi logic lọc nằm ở đây, không viết lại ở view.
"""
from django.db.models import Exists, OuterRef, Q

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
