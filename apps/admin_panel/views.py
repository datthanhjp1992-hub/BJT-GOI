"""
Khu vực quản trị — SC07_QuanTriAdmin.

PHẠM VI CÓ CHỦ ĐÍCH: đây chỉ là bảng TỔNG QUAN (số liệu + người dùng mới
nhất). Mọi thao tác thêm/sửa/xoá đẩy sang Django admin ở `/admin/`, nơi cả 6
app đã đăng ký model sẵn. Viết lại CRUD ở đây là làm lại thứ Django cho không,
và tạo ra hai nơi phải sửa mỗi lần đổi model.

App này KHÔNG có models.py — nó chỉ đọc dữ liệu của app khác.
"""
from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.core.constants import CODE_TYPE_BJT_LEVEL
from apps.core.properties import message
from apps.gamification.models import Contribution
from apps.vocabulary.models import Topic, Vocabulary

User = get_user_model()

# "Chờ duyệt" — xem apps/core/management/commands/seed_mastercode.py,
# code_type 03. Để hằng số ở đây thay vì rải "001" trong truy vấn.
CONTRIBUTION_STATUS_PENDING = "001"

RECENT_USER_LIMIT = 10


def staff_required(view_func):
    """Chỉ cho tài khoản staff vào.

    Chưa đăng nhập -> về trang login (kèm ?next=). Đã đăng nhập mà không phải
    staff -> 403 chứ KHÔNG redirect: người học bấm nhầm link mà bị đá về trang
    đăng nhập sẽ tưởng mình vừa bị đăng xuất.
    """

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied(message("common.error.permission_denied"))
        return view_func(request, *args, **kwargs)

    return _wrapped


@staff_required
def overview_view(request):
    """SC07_QuanTriAdmin — tổng quan hệ thống."""
    stats = {
        "active_users": User.objects.filter(is_active=True).count(),
        "total_vocabulary": Vocabulary.objects.count(),
        "total_topics": Topic.objects.count(),
        "pending_contributions": Contribution.objects.filter(
            status_code=CONTRIBUTION_STATUS_PENDING
        ).count(),
    }
    context = {
        "stats": stats,
        "recent_users": User.objects.order_by("-date_joined")[:RECENT_USER_LIMIT],
        "display_name": (request.user.first_name or "").strip() or request.user.get_username(),
        "bjt_level_code_type": CODE_TYPE_BJT_LEVEL,
        "active_admin_nav": "overview",
    }
    return render(request, "admin_panel/overview.html", context)
