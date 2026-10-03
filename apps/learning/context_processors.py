"""Số liệu học tập cần ở MỌI trang (sidebar) — spec.md T3.4.

`due_badge`: số từ đến hạn ôn hôm nay, hiện cạnh mục "Ôn tập" của sidebar.
Đọc LƯỜI (SimpleLazyObject): chỉ trang nào thật sự in sidebar mới tốn một
lần đọc cache — fragment thẻ học (X-Card-Partial) và trang khách không tốn gì.
Giá trị cache 60 giây theo user (`services.get_due_badge_count`), và được xoá
ngay khi người học chấm/hoàn tác một từ để badge không "đứng hình" cả phút.
"""
from django.utils.functional import SimpleLazyObject

from . import services


def learning_badges(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"due_badge": SimpleLazyObject(lambda: services.get_due_badge_count(user))}
