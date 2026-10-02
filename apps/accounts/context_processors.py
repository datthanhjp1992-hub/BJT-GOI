"""Bơm theme của user vào mọi template để base.html nạp đúng file CSS
(theme_a.css / theme_b.css / theme_c.css) và đặt chế độ sáng/tối
(<html data-scheme="...">, spec.md T2.3).
"""
from apps.core.constants import COLOR_SCHEME_AUTO, COLOR_SCHEMES

DEFAULT_THEME = "A"
VALID_THEMES = {"A", "B", "C"}


def ui_theme(request):
    """Trả về mã theme ĐÃ được kiểm tra hợp lệ.

    Phải chặn giá trị lạ ở đây vì base.html dựng tên file bằng cách nối chuỗi:
    `theme_{{ ui_theme|lower }}.css`. Trên production, WhiteNoise dùng
    CompressedManifestStaticFilesStorage — tên file không có trong manifest sẽ
    ném ValueError và làm 500 TOÀN BỘ trang, không chỉ mất màu. Một hàng user
    cũ có ui_theme rỗng (import dữ liệu, tạo bằng SQL tay) là đủ để dính.
    """
    theme = DEFAULT_THEME
    # Khách chưa đăng nhập: theo thiết bị. Giá trị lạ cũng rơi về "auto" —
    # CSS chỉ có bảng màu cho đúng các mã trong COLOR_SCHEMES.
    scheme = COLOR_SCHEME_AUTO
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        candidate = (user.ui_theme or "").strip().upper()
        if candidate in VALID_THEMES:
            theme = candidate
        candidate = (getattr(user, "color_scheme", "") or "").strip().lower()
        if candidate in COLOR_SCHEMES:
            scheme = candidate
    return {"ui_theme": theme, "color_scheme": scheme}
