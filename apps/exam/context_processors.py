"""Badge Sổ câu sai ở sidebar (docs/SPEC_KIEM_TRA.md T7.8).

Đọc LƯỜI (SimpleLazyObject) như apps.learning.context_processors: chỉ trang nào thật
sự in sidebar mới tốn một câu COUNT (chỉ mục user + cleared_at).
"""
from django.utils.functional import SimpleLazyObject

from .services import wrongbook


def exam_badges(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"wrongbook_badge": SimpleLazyObject(lambda: wrongbook.open_count(user))}
