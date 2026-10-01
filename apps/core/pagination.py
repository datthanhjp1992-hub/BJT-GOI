"""
Phân trang dùng chung có "số dòng mỗi trang" do người dùng chọn.

Dùng ở: SC05 (bảng từ vựng), SC15 (bảng ôn tập theo chủ đề).
Template đi kèm:
  templates/partials/per_page_form.html — ô "Hiển thị [10] dòng / trang"
  templates/partials/pager.html         — ‹ 1 2 … 6 ›

Cả hai chỉ cần dict trả về từ `paginate()` (đặt vào context dưới tên `pager`)
cộng với `pager_query` — đuôi query string giữ lại các tham số khác của trang.
"""
from django.core.paginator import Paginator
from django.http import QueryDict

PAGE_PARAM = "page"
PER_PAGE_PARAM = "per_page"
PER_PAGE_CHOICES = (5, 10, 20, 50, 100)
DEFAULT_PER_PAGE = 10


def clean_per_page(raw, choices=PER_PAGE_CHOICES, default=DEFAULT_PER_PAGE):
    """Giá trị lạ (sửa URL bằng tay) rơi về mặc định thay vì báo lỗi."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value in choices else default


def paginate(items, page_number, per_page, keep=None):
    """Phân trang `items` và dựng sẵn mọi thứ template cần.

    `keep` — QueryDict (hoặc dict) các tham số phải giữ khi lật trang / đổi số
    dòng; KHÔNG chứa `page` và `per_page` (hàm tự thêm).
    """
    paginator = Paginator(items, per_page)
    page = paginator.get_page(page_number)

    params = QueryDict(mutable=True)
    if keep:
        if isinstance(keep, QueryDict):
            for key in keep:
                params.setlist(key, keep.getlist(key))
        else:
            for key, value in keep.items():
                params[key] = value
    params.pop(PAGE_PARAM, None)
    params.pop(PER_PAGE_PARAM, None)

    hidden = [(k, v) for k in params for v in params.getlist(k)]
    params[PER_PAGE_PARAM] = str(per_page)
    return {
        "page_obj": page,
        "paginator": paginator,
        "per_page": per_page,
        "per_page_choices": PER_PAGE_CHOICES,
        # Đuôi cho link phân trang: "&...&per_page=N" (không có `page`).
        "query": "&" + params.urlencode(),
        # Input ẩn cho form chọn số dòng (không có `page`, `per_page`).
        "hidden_fields": hidden,
        # 1 2 … 5 [6] 7 … 12
        "page_range": list(paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
        "ellipsis": paginator.ELLIPSIS,
    }
