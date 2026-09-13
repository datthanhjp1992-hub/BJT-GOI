"""
File chuyển đổi qua lại cho bảng MasterCode — nguồn dữ liệu DUY NHẤT cho mọi
cặp (code <-> code_name) trong hệ thống (cấp độ BJT, theme giao diện, loại/
trạng thái góp ý, loại hành động tính điểm, tên từng bậc danh hiệu...).

Mục tiêu (theo yêu cầu "không hardcode"): mọi nơi cần hiển thị tên từ 1 mã,
hoặc cần danh sách lựa chọn cho <select>/ModelForm, đều gọi qua các hàm ở
đây — KHÔNG tự viết `if code == "001": return "..."` hay `choices=[...]`
cứng ở model/view/template nào khác.

Có cache 2 lớp (theo tiến trình, dùng Django cache framework — dev mặc định
là LocMemCache) để tránh query MasterCode lặp lại trên mỗi request; cache
được xoá tự động khi MasterCode thay đổi, xem apps/core/signals.py.
"""
from django.core.cache import cache
from django.db import DatabaseError

# Bootstrap guard -------------------------------------------------------------
# `choices=<callable>` khiến Django gọi các hàm dưới đây ngay trong system
# checks (_check_choices), tức là TRƯỚC khi `migrate` kịp tạo bảng
# core_mastercode. Trên một database trống — đúng tình huống deploy lần đầu
# lên Supabase — điều đó làm chính lệnh `migrate` chết vì
# ProgrammingError: relation "core_mastercode" does not exist.
#
# Vì vậy mọi hàm đọc MasterCode đều fail-soft: DB chưa sẵn sàng thì trả giá
# trị rỗng và KHÔNG cache (để lần gọi sau, khi bảng đã có, đọc lại bình
# thường). Seed thiếu vẫn hiện ra ở UI dưới dạng ô rỗng như trước.
def _safe(query_fn, default):
    try:
        return query_fn()
    except DatabaseError:
        return default

CACHE_PREFIX = "mastercode"
CACHE_TTL_SECONDS = 300


def _db_ready():
    """True nếu bảng core_mastercode đã tồn tại và query được."""
    from apps.core.models import MasterCode

    try:
        MasterCode.objects.exists()
        return True
    except DatabaseError:
        return False


def _key_name(code_type, code):
    return f"{CACHE_PREFIX}:name:{code_type}:{code}"


def _key_list(code_type, include_inactive):
    return f"{CACHE_PREFIX}:list:{code_type}:{'all' if include_inactive else 'active'}"


def _key_children(code_type, mother_code):
    return f"{CACHE_PREFIX}:children:{code_type}:{mother_code}"


def get_code_name(code_type, code, default=""):
    """
    code -> code_name.
    Ví dụ: get_code_name(CODE_TYPE_BADGE_CONTRIBUTION, "003") -> "Chuyên Gia"

    Không raise nếu thiếu seed data — trả `default` để UI không vỡ, nhưng sẽ
    khiến màn hình hiển thị rỗng/"—", nên nhớ seed đủ trước khi demo.
    """
    if not code_type or not code:
        return default
    key = _key_name(code_type, code)
    cached = cache.get(key)
    if cached is not None:
        return cached or default

    from apps.core.models import MasterCode  # tránh import vòng lúc app load

    row = _safe(
        lambda: MasterCode.objects.filter(code_type=code_type, code=code, is_active=True).first(),
        None,
    )
    if row is None and not _db_ready():
        return default  # DB chưa có bảng — đừng cache trạng thái tạm thời này
    name = row.code_name if row else ""
    cache.set(key, name, CACHE_TTL_SECONDS)
    return name or default


def get_code_by_name(code_type, code_name):
    """
    Chiều ngược lại: code_name -> code. Dùng khi nhận dữ liệu từ nơi chỉ biết
    tên hiển thị (vd import Excel ghi "J4" thay vì mã nội bộ).
    Trả None nếu không khớp — người gọi tự quyết định raise hay bỏ qua dòng.
    """
    from apps.core.models import MasterCode

    row = _safe(
        lambda: MasterCode.objects.filter(
            code_type=code_type, code_name__iexact=code_name.strip(), is_active=True
        ).first(),
        None,
    )
    return row.code if row else None


def get_choices(code_type, include_inactive=False):
    """
    Trả `[(code, code_name), ...]` đã sort theo sort_order rồi code — dùng
    thẳng làm `choices=` cho CharField/ModelForm hoặc render <select> trong
    template (`{% for code, name in choices %}`).
    """
    key = _key_list(code_type, include_inactive)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from apps.core.models import MasterCode

    def _query():
        qs = MasterCode.objects.filter(code_type=code_type)
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return list(qs.order_by("sort_order", "code").values_list("code", "code_name"))

    result = _safe(_query, None)
    if result is None:
        return []  # DB chưa sẵn sàng — không cache
    cache.set(key, result, CACHE_TTL_SECONDS)
    return result


def get_children(code_type, mother_code):
    """
    Lấy các code con của 1 code cha TRONG CÙNG code_type — dùng cho các
    code_type có phân cấp (vd trạng thái góp ý "Đã xử lý" gom "Đã duyệt" +
    "Từ chối"). Trả `[(code, code_name), ...]`.
    """
    key = _key_children(code_type, mother_code)
    cached = cache.get(key)
    if cached is not None:
        return cached

    from apps.core.models import MasterCode

    result = _safe(
        lambda: list(
            MasterCode.objects.filter(code_type=code_type, mother_code=mother_code, is_active=True)
            .order_by("sort_order", "code")
            .values_list("code", "code_name")
        ),
        None,
    )
    if result is None:
        return []  # DB chưa sẵn sàng — không cache
    cache.set(key, result, CACHE_TTL_SECONDS)
    return result


def invalidate_cache(code_type=None, code=None):
    """
    Xoá cache liên quan tới 1 (code_type, code) hoặc cả 1 code_type.
    Được gọi tự động từ signal post_save/post_delete của MasterCode
    (apps/core/signals.py) — không cần gọi tay trừ khi bulk-update thẳng
    bằng SQL (bypass signal).
    """
    if code_type and code:
        cache.delete(_key_name(code_type, code))
    if code_type:
        cache.delete(_key_list(code_type, True))
        cache.delete(_key_list(code_type, False))
        # xoá luôn cache "children" — không biết mother_code nào bị ảnh hưởng
        # nên đơn giản là để nó tự hết hạn theo CACHE_TTL_SECONDS thay vì dò hết.
