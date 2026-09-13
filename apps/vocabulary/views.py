"""
View của app vocabulary: SC05_DanhSachTuVung.

Một view duy nhất phục vụ hai URL:
    /vocabulary/                  -> toàn bộ từ vựng
    /vocabulary/topic/<slug>/     -> từ vựng trong một chủ đề
Khác nhau đúng một biến `topic`, nên tách ra hai hàm chỉ để trùng lặp code.
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import QueryDict
from django.shortcuts import get_object_or_404, render

from apps.core import mastercode
from apps.core.constants import CODE_TYPE_BJT_LEVEL
from apps.learning.models import UserVocabularyProgress

from .models import Topic, Vocabulary

PAGE_SIZE = 25

# Trần kết quả cho nhánh tìm kiếm. `VocabularyQuerySet.search()` sắp xếp theo
# điểm trigram nên PHẢI cắt ở tầng SQL (nếu không Postgres phải chấm điểm cả
# bảng); 200 là quá đủ cho người học lướt xem, quá số này thì gõ từ khoá rõ hơn.
SEARCH_LIMIT = 200

STATUS_NEW = "new"
STATUS_LEARNING = "learning"
STATUS_MASTERED = "mastered"


def _pagination_query(request):
    """Chuỗi query giữ lại q/level khi bấm sang trang khác (bỏ `page`)."""
    params = QueryDict(mutable=True)
    params.update(request.GET)
    params.pop("page", None)
    encoded = params.urlencode()
    return ("&" + encoded) if encoded else ""


def _attach_study_status(user, words, fallback_topic=None):
    """Gắn `study_status` + `primary_topic` cho các từ trên TRANG HIỆN TẠI.

    Chỉ query tiến độ của đúng số từ đang hiển thị (25), không phải cả bảng.
    `primary_topic` dùng để dựng link "Ôn tập →" (route flashcard cần slug
    chủ đề); từ mồ côi không thuộc chủ đề nào thì để None và template ẩn link.
    """
    word_ids = [word.pk for word in words]
    if not word_ids:
        return words

    mastered_by_id = dict(
        UserVocabularyProgress.objects.filter(
            user=user, vocabulary_id__in=word_ids
        ).values_list("vocabulary_id", "is_mastered")
    )
    for word in words:
        if word.pk not in mastered_by_id:
            word.study_status = STATUS_NEW
        elif mastered_by_id[word.pk]:
            word.study_status = STATUS_MASTERED
        else:
            word.study_status = STATUS_LEARNING

        if fallback_topic is not None:
            word.primary_topic = fallback_topic
        else:
            topics = list(word.topics.all())  # đã prefetch, không phát sinh query
            word.primary_topic = topics[0] if topics else None
    return words


@login_required
def vocabulary_list_view(request, topic_slug=None):
    """SC05_DanhSachTuVung."""
    topic = get_object_or_404(Topic, slug=topic_slug) if topic_slug else None
    query = (request.GET.get("q") or "").strip()
    level = (request.GET.get("level") or "").strip()

    words = Vocabulary.objects.prefetch_related("topics")
    if topic is not None:
        words = words.filter(topics=topic)
    if level:
        words = words.filter(bjt_level=level)

    if query:
        # .search() trả về queryset ĐÃ cắt (slice) — mọi filter phải đứng trước.
        words = words.search(query, limit=SEARCH_LIMIT)
    else:
        words = words.order_by("bjt_level", "word")

    paginator = Paginator(words, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    _attach_study_status(request.user, page.object_list, fallback_topic=topic)

    context = {
        "topic": topic,
        "topics": Topic.objects.all(),
        "page_obj": page,
        "paginator": paginator,
        "total_count": paginator.count,
        "query": query,
        "selected_level": level,
        "level_choices": mastercode.get_choices(CODE_TYPE_BJT_LEVEL),
        "bjt_level_code_type": CODE_TYPE_BJT_LEVEL,
        "pagination_query": _pagination_query(request),
        "active_nav": "vocabulary",
    }
    return render(request, "vocabulary/list.html", context)
