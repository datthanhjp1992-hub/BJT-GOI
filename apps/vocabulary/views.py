"""
View của app vocabulary: SC05_DanhSachTuVung.

Một view duy nhất phục vụ hai URL:
    /vocabulary/                  -> toàn bộ từ vựng
    /vocabulary/topic/<slug>/     -> từ vựng trong một chủ đề
Khác nhau đúng một biến `topic`, nên tách ra hai hàm chỉ để trùng lặp code.

Bộ lọc chủ đề cho phép CHỌN NHIỀU (13/09/2026): các chủ đề đang chọn nằm ở
query string `?topic=slug&topic=slug`, quan hệ HOẶC (một từ chỉ cần thuộc một
trong các chủ đề đã chọn). Route `/topic/<slug>/` giữ nguyên để không gãy link
cũ — slug trên route được gộp vào tập đang chọn.
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import QueryDict
from django.shortcuts import get_object_or_404, render

from apps.learning.models import UserVocabularyProgress

from .models import Topic, Vocabulary

PAGE_SIZE = 25

# Trần kết quả cho nhánh tìm kiếm. `VocabularyQuerySet.search()` sắp xếp theo
# điểm trigram nên PHẢI cắt ở tầng SQL (nếu không Postgres phải chấm điểm cả
# bảng); 200 là quá đủ cho người học lướt xem, quá số này thì gõ từ khoá rõ hơn.
SEARCH_LIMIT = 200

# Tên tham số chứa slug chủ đề trên query string (lặp lại được).
TOPIC_PARAM = "topic"

STATUS_NEW = "new"
STATUS_LEARNING = "learning"
STATUS_MASTERED = "mastered"


def _pagination_query(request, selected_slugs):
    """Chuỗi query giữ lại từ khoá + chủ đề đang lọc khi bấm sang trang khác.

    Bỏ `page`, và dựng lại `topic` từ tập đã chuẩn hoá (slug rác bị loại bỏ,
    slug trên route được đưa vào) để trang 2 lọc y hệt trang 1.
    """
    params = QueryDict(mutable=True)
    params.update(request.GET)
    params.pop("page", None)
    params.setlist(TOPIC_PARAM, list(selected_slugs))
    encoded = params.urlencode()
    return ("&" + encoded) if encoded else ""


def _topic_query(slugs, query):
    """Query string cho một tập chủ đề (dùng cho link bật/tắt trên thanh lọc)."""
    params = QueryDict(mutable=True)
    if query:
        params["q"] = query
    params.setlist(TOPIC_PARAM, list(slugs))
    encoded = params.urlencode()
    return ("?" + encoded) if encoded else ""


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
    # Slug sai trên ROUTE là lỗi 404 (link hỏng); slug sai trên QUERY STRING thì
    # lờ đi — người dùng sửa URL bằng tay không đáng phải nhận trang lỗi.
    route_topic = get_object_or_404(Topic, slug=topic_slug) if topic_slug else None
    query = (request.GET.get("q") or "").strip()

    all_topics = list(Topic.objects.all())
    topic_by_slug = {t.slug: t for t in all_topics}

    requested = list(request.GET.getlist(TOPIC_PARAM))
    if route_topic is not None:
        requested.insert(0, route_topic.slug)

    selected_slugs = []  # giữ thứ tự bấm, bỏ trùng và bỏ slug không tồn tại
    for slug in requested:
        if slug in topic_by_slug and slug not in selected_slugs:
            selected_slugs.append(slug)
    selected_topics = [topic_by_slug[slug] for slug in selected_slugs]

    words = Vocabulary.objects.prefetch_related("topics")
    if selected_topics:
        # HOẶC: từ chỉ cần thuộc một trong các chủ đề đã chọn. `distinct()` vì
        # join M2M nhân bản dòng khi một từ khớp nhiều chủ đề đang chọn.
        words = words.filter(topics__in=selected_topics).distinct()

    if query:
        # .search() trả về queryset ĐÃ cắt (slice) — mọi filter phải đứng trước.
        words = words.search(query, limit=SEARCH_LIMIT)
    else:
        words = words.order_by("word")

    paginator = Paginator(words, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    # Chỉ "mượn" chủ đề cho link ôn tập khi đang lọc đúng MỘT chủ đề; nhiều chủ
    # đề thì không có chủ đề nào là hiển nhiên, để primary_topic tự suy ra.
    only_topic = selected_topics[0] if len(selected_topics) == 1 else None
    _attach_study_status(request.user, page.object_list, fallback_topic=only_topic)

    # Mỗi thẻ trên thanh lọc là một link BẬT/TẮT: đang chọn thì link bỏ nó ra,
    # chưa chọn thì link thêm nó vào — bấm lần hai chính là bỏ lọc.
    topic_filters = []
    for t in all_topics:
        is_selected = t.slug in selected_slugs
        if is_selected:
            next_slugs = [s for s in selected_slugs if s != t.slug]
        else:
            next_slugs = selected_slugs + [t.slug]
        topic_filters.append(
            {"topic": t, "is_selected": is_selected, "query": _topic_query(next_slugs, query)}
        )

    context = {
        "topic": only_topic,  # tương thích ngược: template/test cũ đọc biến này
        "topics": all_topics,
        "selected_topics": selected_topics,
        "topic_filters": topic_filters,
        "clear_query": _topic_query([], query),
        "page_obj": page,
        "paginator": paginator,
        "total_count": paginator.count,
        "query": query,
        "pagination_query": _pagination_query(request, selected_slugs),
        "active_nav": "vocabulary",
    }
    return render(request, "vocabulary/list.html", context)
