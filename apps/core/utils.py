"""Small shared helpers used by multiple apps."""


def chunked(iterable, size):
    """Yield successive chunks of `size` items from iterable."""
    buf = []
    for item in iterable:
        buf.append(item)
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf
# ---------------------------------------------------------------------------
# Thanh lọc theo chủ đề (SC05 danh sách từ vựng, SC10 tạo phiếu)
#
# Chọn được NHIỀU chủ đề cùng lúc, quan hệ HOẶC. Trạng thái nằm ở query string
# `?topic=slug&topic=slug` nên bookmark/chia sẻ/back được, và thanh lọc vẫn
# chạy đúng khi trình duyệt tắt JavaScript — mỗi thẻ chỉ là một cái link.
# ---------------------------------------------------------------------------
TOPIC_PARAM = "topic"


def _query_string(slugs, keep):
    """Dựng query string cho một tập chủ đề, giữ lại các tham số trong `keep`."""
    from django.http import QueryDict

    params = QueryDict(mutable=True)
    for name, value in keep.items():
        if value:
            params[name] = value
    params.setlist(TOPIC_PARAM, list(slugs))
    encoded = params.urlencode()
    return ("?" + encoded) if encoded else ""


def topic_filter_bar(request, topics, forced_slug=None, keep=None):
    """Dữ liệu cho thanh lọc chủ đề nhiều-lựa-chọn.

    `topics`        — danh sách Topic hiển thị trên thanh lọc (đã sắp xếp sẵn).
    `forced_slug`   — slug đến từ ROUTE (vd /vocabulary/topic/<slug>/), luôn
                      được coi là đang chọn.
    `keep`          — dict tham số khác cần giữ lại trong link (vd {"q": ...}).

    Trả về (selected_topics, filters, clear_query):
      selected_topics — list Topic đang chọn, theo thứ tự xuất hiện trên URL.
      filters         — list dict {topic, is_selected, query} cho từng thẻ;
                        `query` là link BẬT/TẮT: đang chọn thì bỏ nó ra, chưa
                        chọn thì thêm nó vào — bấm lần hai chính là bỏ lọc.
      clear_query     — link của thẻ "Tất cả" (xoá sạch chủ đề, giữ `keep`).

    Slug không tồn tại trên query string bị LỜ ĐI chứ không 404: người dùng
    sửa URL bằng tay không đáng phải nhận trang lỗi.
    """
    keep = keep or {}
    topics = list(topics)
    known = {t.slug for t in topics}

    requested = list(request.GET.getlist(TOPIC_PARAM))
    if forced_slug:
        requested.insert(0, forced_slug)

    selected_slugs = []  # giữ thứ tự bấm, bỏ trùng và bỏ slug lạ
    for slug in requested:
        if slug in known and slug not in selected_slugs:
            selected_slugs.append(slug)

    by_slug = {t.slug: t for t in topics}
    selected_topics = [by_slug[slug] for slug in selected_slugs]

    filters = []
    for topic in topics:
        is_selected = topic.slug in selected_slugs
        if is_selected:
            next_slugs = [s for s in selected_slugs if s != topic.slug]
        else:
            next_slugs = selected_slugs + [topic.slug]
        filters.append({
            "topic": topic,
            "is_selected": is_selected,
            "query": _query_string(next_slugs, keep),
        })

    return selected_topics, filters, _query_string([], keep)
