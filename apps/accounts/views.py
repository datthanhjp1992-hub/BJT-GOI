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

from .forms import LoginForm, ProfileForm, RegisterForm, SettingsForm

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
    trang khác cũng đá được người dùng ra ngoài). Nút Đăng xuất ở topbar là
    một <form method="post"> — xem templates/partials/topbar.html.
    """
    if request.user.is_authenticated:
        logout(request)
        flash.info(request, message("accounts.logout.success"))
    return redirect("accounts:login")


@login_required
def profile_view(request):
    """SC09_ThongTinCaNhan."""
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        flash.success(request, message("common.success.saved"))
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def settings_view(request):
    """SC08_CaiDat. Đổi theme là đổi luôn file CSS mà base.html nạp."""
    previous_theme = request.user.ui_theme
    form = SettingsForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        # Đổi mật khẩu không nằm ở form này, nhưng gọi cho chắc: giữ session
        # sống nếu sau này thêm field ảnh hưởng tới password hash.
        update_session_auth_hash(request, user)
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
    return render(request, "accounts/settings.html", {"form": form})
