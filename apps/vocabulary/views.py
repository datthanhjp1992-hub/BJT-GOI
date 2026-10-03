"""
View của app vocabulary: SC05_DanhSachTuVung.

Một view duy nhất phục vụ hai URL:
    /vocabulary/                  -> thư viện từ vựng
    /vocabulary/topic/<slug>/     -> mở sẵn với một chủ đề đã chọn

Sửa 01/10/2026:
  * Bỏ ô "Tìm kiếm từ vựng" khỏi form — chỉ lọc theo chủ đề (+ trạng thái).
    `?q=` vẫn được đọc để link "tra trong từ vựng" từ màn Kính ngữ không gãy;
    khi có `q`, trang hiện một chip "Đang tìm …" kèm nút bỏ.
  * Số từ mỗi phiên học mặc định = Tất cả.
  * Bảng kết quả: người dùng chọn 5/10/20/50/100 dòng mỗi trang (mặc định 10)
    qua tham số `per_page`; phân trang có số trang + dấu "…".

Luồng dùng trang (sửa 18/09/2026):
  1. Vào trang -> CHỈ hiện khu bộ lọc, KHÔNG truy vấn từ vựng. Kho từ tới vài
     nghìn từ nên tải sẵn một trang 50 dòng mà người dùng chưa cần là lãng phí.
  2. Bấm "Lọc" -> form GET nạp lại trang kèm tham số -> bảng kết quả hiện ra,
     `per_page` dòng mỗi trang (mặc định 10), phân trang bên dưới.
  3. Bấm "Bắt đầu học" dưới chân bảng -> POST sang learning:study_start, học
     TOÀN BỘ từ khớp bộ lọc (gộp nhiều chủ đề vào một hàng đợi).

Vì trạng thái bộ lọc nằm ở query string nên trang vẫn bookmark/chia sẻ/back
được và chạy đúng khi trình duyệt tắt JavaScript.
"""
import re

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import QueryDict
from django.shortcuts import get_object_or_404, render

from apps.core import pagination
from apps.core.properties import label
from apps.core.utils import TOPIC_PARAM, topic_filter_bar
from apps.learning.models import UserVocabularyProgress

from . import selectors
from .models import Topic

# Số dòng mỗi trang của bảng kết quả — người dùng chọn ngay trên bảng.
# Logic dùng chung nằm ở apps.core.pagination; giữ tên cũ để test/code ngoài
# import không gãy.
PER_PAGE_PARAM = pagination.PER_PAGE_PARAM
PER_PAGE_CHOICES = pagination.PER_PAGE_CHOICES
DEFAULT_PER_PAGE = pagination.DEFAULT_PER_PAGE
PAGE_SIZE = DEFAULT_PER_PAGE
clean_per_page = pagination.clean_per_page

# Giữ lại tên cũ để test/code ngoài import không gãy.
SEARCH_LIMIT = selectors.SEARCH_LIMIT
STATUS_NEW = selectors.STATUS_NEW
STATUS_LEARNING = selectors.STATUS_LEARNING
STATUS_MASTERED = selectors.STATUS_MASTERED


def _filter_params(selected_slugs, statuses, query, session_limit):
    """Bộ lọc ĐÃ CHUẨN HOÁ dưới dạng QueryDict (không có `page`/`per_page`).

    Dựng lại từ giá trị sạch thay vì chép request.GET: giá trị rác bị loại,
    slug trên route được đưa vào, nên trang 2 lọc y hệt trang 1.
    """
    params = QueryDict(mutable=True)
    params[selectors.FILTERED_PARAM] = "1"
    params.setlist(TOPIC_PARAM, list(selected_slugs))
    params.setlist(selectors.STATUS_PARAM, list(statuses))
    if query:
        params[selectors.SEARCH_PARAM] = query
    params[selectors.LIMIT_PARAM] = str(session_limit)
    return params


def _natural_key(topic):
    """Khoá sắp xếp tự nhiên: so số theo giá trị, so chữ không phân biệt hoa thường."""
    text = topic.name_ja or topic.name
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


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

    # Số từ mỗi chủ đề hiện cạnh tên trong dropdown. Chỉ đếm trên bảng nối
    # VocabularyTopic (GROUP BY nhỏ), không chạm vào bảng từ vựng.
    # Query có GROUP BY thì Django bỏ qua Meta.ordering, nên phải tự sắp: theo
    # thứ tự "tự nhiên" để レッスン2 đứng trước レッスン10.
    all_topics = sorted(
        Topic.objects.annotate(word_count=Count("vocabulary_links")),
        key=_natural_key,
    )
    selected_topics, topic_filters, clear_query = topic_filter_bar(
        request,
        all_topics,
        forced_slug=route_topic.slug if route_topic else None,
        keep={selectors.SEARCH_PARAM: query, selectors.FILTERED_PARAM: "1"},
    )
    selected_slugs = [t.slug for t in selected_topics]
    statuses = selectors.clean_statuses(request.GET.getlist(selectors.STATUS_PARAM))
    session_limit = selectors.clean_session_limit(
        request.GET.get(selectors.LIMIT_PARAM),
        default=selectors.LIBRARY_DEFAULT_SESSION_LIMIT,
    )
    per_page = clean_per_page(request.GET.get(PER_PAGE_PARAM))
    is_filtered = selectors.is_filter_request(request.GET, forced=bool(route_topic))

    # Nhiều chủ đề thì không chủ đề nào là "chủ đề của trang".
    only_topic = selected_topics[0] if len(selected_topics) == 1 else None

    context = {
        "topic": only_topic,  # tương thích ngược: template/test cũ đọc biến này
        "topics": all_topics,
        "selected_topics": selected_topics,
        # Tiêu đề trang (partials/page_header.html nhận chuỗi): tên các chủ đề
        # đang lọc, không lọc chủ đề nào thì "Tất cả từ vựng".
        "page_title": " + ".join(
            f"{t.icon_emoji} {t.display_name}".strip() for t in selected_topics
        ) or label("vocabulary.list.title.all"),
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
        "limit_choices": selectors.LIBRARY_SESSION_LIMIT_CHOICES,
        "is_filtered": is_filtered,
        "page_size": per_page,
        "per_page": per_page,
        "per_page_choices": PER_PAGE_CHOICES,
        # Link bỏ từ khoá `q` (chỉ đến từ deep link, form không còn ô tìm).
        "clear_search_query": "",
        "active_nav": "vocabulary",
        # Mặc định của nhánh "chưa lọc" — template không phải kiểm tra None.
        "page_obj": None,
        "paginator": None,
        "total_count": 0,
        "pagination_query": "",
        "page_range": [],
        "filter_hidden_fields": [],
    }
    if query:
        no_search = _filter_params(selected_slugs, statuses, "", session_limit)
        no_search[PER_PAGE_PARAM] = str(per_page)
        context["clear_search_query"] = "?" + no_search.urlencode()

    if not is_filtered:
        # Chưa bấm Lọc: KHÔNG chạm vào bảng từ vựng.
        return render(request, "vocabulary/list.html", context)

    words = selectors.filter_vocabulary(
        request.user, topics=selected_topics, query=query, statuses=statuses
    )
    params = _filter_params(selected_slugs, statuses, query, session_limit)
    pager = pagination.paginate(words, request.GET.get(pagination.PAGE_PARAM), per_page, keep=params)
    page = pager["page_obj"]
    # Chỉ "mượn" chủ đề cho link học khi đang lọc đúng MỘT chủ đề.
    _attach_study_status(request.user, page.object_list, fallback_topic=only_topic)

    context.update({
        "pager": pager,
        "page_obj": page,
        "paginator": pager["paginator"],
        "total_count": pager["paginator"].count,
        "pagination_query": pager["query"],
        "page_range": pager["page_range"],
        "page_ellipsis": pager["ellipsis"],
        "filter_hidden_fields": pager["hidden_fields"],
    })
    return render(request, "vocabulary/list.html", context)
