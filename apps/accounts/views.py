"""
View cho khu vực tài khoản:
    SC01 Đăng nhập · SC02 Đăng ký · SC08 Cài đặt · SC09 Thông tin cá nhân.

Toàn bộ chuỗi hiển thị đi qua `apps.core.properties`; view chỉ điều phối
form + redirect, không tự dựng chuỗi tiếng Việt.
"""
from django.contrib import messages as flash
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core import mastercode
from apps.core.constants import CODE_TYPE_UI_THEME
from apps.core.properties import message
from apps.learning import services as learning_services

from .forms import (
    LoginForm,
    PasswordUpdateForm,
    ProfileForm,
    RegisterForm,
    SettingsForm,
)

REDIRECT_FIELD_NAME = "next"
DEFAULT_REDIRECT = "learning:dashboard"


def _safe_redirect_target(request, fallback=DEFAULT_REDIRECT):
    """URL để quay về sau khi đăng nhập/đăng ký.

    Chỉ chấp nhận `?next=` trỏ về chính host này — chặn open redirect
    (kiểu `/accounts/login/?next=https://trang-lua-dao...`).
    """
    target = request.POST.get(REDIRECT_FIELD_NAME) or request.GET.get(REDIRECT_FIELD_NAME)
    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return reverse(fallback)


def _display_name(user):
    """Tên hiển thị trong lời chào — họ tên đầy đủ, thiếu thì lấy username."""
    return (user.first_name or "").strip() or user.get_username()


def login_view(request):
    """SC01_DangNhap."""
    if request.user.is_authenticated:
        return redirect(_safe_redirect_target(request))

    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        flash.success(request, message("accounts.login.success", name=_display_name(user)))
        return redirect(_safe_redirect_target(request))

    return render(request, "accounts/login.html", {
        "form": form,
        # Chuyển tiếp ?next= vào ô hidden của form để POST không đánh mất đích đến.
        REDIRECT_FIELD_NAME: request.GET.get(REDIRECT_FIELD_NAME, ""),
    })


def register_view(request):
    """SC02_DangKy. Đăng ký xong đăng nhập luôn, khỏi bắt nhập lại."""
    if request.user.is_authenticated:
        return redirect(DEFAULT_REDIRECT)

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        flash.success(request, message("accounts.register.success"))
        return redirect(DEFAULT_REDIRECT)

    return render(request, "accounts/register.html", {"form": form})


@require_POST
def logout_view(request):
    """Chỉ nhận POST: đăng xuất bằng link GET là bị CSRF (một thẻ <img> trên
    trang khác cũng đá được người dùng ra ngoài). Nút Đăng xuất là một
    <form method="post"> — xem templates/partials/sidebar.html (23/09/2026,
    trước đó ở templates/partials/topbar.html).
    """
    if request.user.is_authenticated:
        logout(request)
        flash.info(request, message("accounts.logout.success"))
    return redirect("accounts:login")


@login_required
def profile_view(request):
    """SC09_ThongTinCaNhan.

    Số liệu (từ đã thuộc/ngày liên tục/điểm) và danh sách chủ đề gần đây tính
    ở apps.learning.services — cùng nguồn với SC03 Trang chủ, view ở đây chỉ
    lắp thêm context, không tự viết truy vấn (xem apps.learning.services để
    biết vì sao get_recent_topics() khác get_topic_in_progress()).
    """
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        flash.success(request, message("common.success.saved"))
        return redirect("accounts:profile")

    stats = learning_services.get_learning_stats(request.user)
    context = {
        "form": form,
        "display_name": (request.user.first_name or "").strip() or request.user.get_username(),
        "stats": stats,
        "joined_date": request.user.date_joined.strftime("%m/%Y"),
        "recent_topics": learning_services.get_recent_topics(request.user),
    }
    return render(request, "accounts/profile.html", context)


@login_required
def settings_view(request):
    """SC08_CaiDat. Đổi theme là đổi luôn file CSS mà base.html nạp.

    Trang có HAI form độc lập cùng POST về đây, phân biệt bằng ô ẩn `section`:

        "preferences" — giao diện, mục tiêu, múi giờ, thông báo
        "password"    — đổi mật khẩu

    Chỉ form được gửi mới nhận `request.POST`; form còn lại dựng ở trạng thái
    chưa bind nên hiện đúng giá trị đang lưu, không kéo theo lỗi đỏ oan của
    khu bên cạnh. Tên ô là `section` chứ không phải `form` — `form` đã là tên
    biến context của template.
    """
    previous_theme = request.user.ui_theme
    section = request.POST.get("section") if request.method == "POST" else None

    settings_form = SettingsForm(
        request.POST if section == "preferences" else None, instance=request.user
    )
    password_form = PasswordUpdateForm(
        request.user, request.POST if section == "password" else None
    )

    if section == "preferences" and settings_form.is_valid():
        user = settings_form.save()
        if user.ui_theme != previous_theme:
            flash.success(request, message(
                "accounts.settings.success.theme_updated",
                theme_name=mastercode.get_code_name(
                    CODE_TYPE_UI_THEME, user.ui_theme, default=user.ui_theme
                ),
            ))
        else:
            flash.success(request, message("common.success.saved"))
        return redirect("accounts:settings")

    if section == "password" and password_form.is_valid():
        user = password_form.save()
        # BẮT BUỘC: đổi mật khẩu làm hash phiên đăng nhập cũ hết hiệu lực, thiếu
        # dòng này thì người dùng bị đá ra trang đăng nhập ngay sau khi đổi.
        update_session_auth_hash(request, user)
        flash.success(request, message("accounts.settings.success.password_changed"))
        return redirect("accounts:settings")

    return render(request, "accounts/settings.html", {
        "form": settings_form,
        "password_form": password_form,
    })
