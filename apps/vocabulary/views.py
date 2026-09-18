"""
View của app vocabulary: SC05_DanhSachTuVung.

Một view duy nhất phục vụ hai URL:
    /vocabulary/                  -> thư viện từ vựng
    /vocabulary/topic/<slug>/     -> mở sẵn với một chủ đề đã chọn

Luồng dùng trang (sửa 18/09/2026):
  1. Vào trang -> CHỈ hiện khu bộ lọc, KHÔNG truy vấn từ vựng. Kho từ tới vài
     nghìn từ nên tải sẵn một trang 50 dòng mà người dùng chưa cần là lãng phí.
  2. Bấm "Lọc" -> form GET nạp lại trang kèm tham số -> bảng kết quả hiện ra,
     50 dòng mỗi trang, phân trang bên dưới.
  3. Bấm "Bắt đầu học" dưới chân bảng -> POST sang learning:study_start, học
     TOÀN BỘ từ khớp bộ lọc (gộp nhiều chủ đề vào một hàng đợi).

Vì trạng thái bộ lọc nằm ở query string nên trang vẫn bookmark/chia sẻ/back
được và chạy đúng khi trình duyệt tắt JavaScript.
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import QueryDict
from django.shortcuts import get_object_or_404, render

from apps.core.utils import TOPIC_PARAM, topic_filter_bar
from apps.learning.models import UserVocabularyProgress

from . import selectors
from .models import Topic

PAGE_SIZE = 50

# Giữ lại tên cũ để test/code ngoài import không gãy.
SEARCH_LIMIT = selectors.SEARCH_LIMIT
STATUS_NEW = selectors.STATUS_NEW
STATUS_LEARNING = selectors.STATUS_LEARNING
STATUS_MASTERED = selectors.STATUS_MASTERED


def _pagination_query(request, selected_slugs, statuses):
    """Chuỗi query giữ lại bộ lọc khi bấm sang trang khác.

    Bỏ `page`, và dựng lại `topic`/`status` từ tập đã chuẩn hoá (giá trị rác bị
    loại bỏ, slug trên route được đưa vào) để trang 2 lọc y hệt trang 1.
    """
    params = QueryDict(mutable=True)
    params.update(request.GET)
    params.pop("page", None)
    params.setlist(TOPIC_PARAM, list(selected_slugs))
    params.setlist(selectors.STATUS_PARAM, list(statuses))
    params[selectors.FILTERED_PARAM] = "1"
    encoded = params.urlencode()
    return ("&" + encoded) if encoded else ""


def _attach_study_status(user, words, fallback_topic=None):
    """Gắn `study_status` + `primary_topic` cho các từ trên TRANG HIỆN TẠI.

    Chỉ query tiến độ của đúng số từ đang hiển thị, không phải cả bảng.
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
    query = (request.GET.get(selectors.SEARCH_PARAM) or "").strip()

    all_topics = list(Topic.objects.all())
    selected_topics, topic_filters, clear_query = topic_filter_bar(
        request,
        all_topics,
        forced_slug=route_topic.slug if route_topic else None,
        keep={selectors.SEARCH_PARAM: query, selectors.FILTERED_PARAM: "1"},
    )
    selected_slugs = [t.slug for t in selected_topics]
    statuses = selectors.clean_statuses(request.GET.getlist(selectors.STATUS_PARAM))
    session_limit = selectors.clean_session_limit(
        request.GET.get(selectors.LIMIT_PARAM, selectors.DEFAULT_SESSION_LIMIT)
    )
    is_filtered = selectors.is_filter_request(request.GET, forced=bool(route_topic))

    # Nhiều chủ đề thì không chủ đề nào là "chủ đề của trang".
    only_topic = selected_topics[0] if len(selected_topics) == 1 else None

    context = {
        "topic": only_topic,  # tương thích ngược: template/test cũ đọc biến này
        "topics": all_topics,
        "selected_topics": selected_topics,
        "topic_filters": topic_filters,
        "clear_query": clear_query,
        "query": query,
        "selected_statuses": statuses,
        "status_filters": [
            {
                "code": code,
                "label_key": selectors.STATUS_LABEL_KEYS[code],
                "is_selected": code in statuses,
            }
            for code in selectors.STATUS_CODES
        ],
        "session_limit": session_limit,
        "limit_choices": selectors.SESSION_LIMIT_CHOICES,
        "is_filtered": is_filtered,
        "page_size": PAGE_SIZE,
        "active_nav": "vocabulary",
        # Mặc định của nhánh "chưa lọc" — template không phải kiểm tra None.
        "page_obj": None,
        "paginator": None,
        "total_count": 0,
        "pagination_query": "",
    }

    if not is_filtered:
        # Chưa bấm Lọc: KHÔNG chạm vào bảng từ vựng.
        return render(request, "vocabulary/list.html", context)

    words = selectors.filter_vocabulary(
        request.user, topics=selected_topics, query=query, statuses=statuses
    )
    paginator = Paginator(words, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    # Chỉ "mượn" chủ đề cho link học khi đang lọc đúng MỘT chủ đề.
    _attach_study_status(request.user, page.object_list, fallback_topic=only_topic)

    context.update({
        "page_obj": page,
        "paginator": paginator,
        "total_count": paginator.count,
        "pagination_query": _pagination_query(request, selected_slugs, statuses),
    })
    return render(request, "vocabulary/list.html", context)
