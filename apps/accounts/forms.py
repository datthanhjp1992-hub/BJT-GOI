"""
Form cho các màn hình tài khoản:
    SC01 Đăng nhập, SC02 Đăng ký, SC08 Cài đặt, SC09 Thông tin cá nhân.

Hai quy ước của repo được áp dụng triệt để ở đây:

1. KHÔNG hardcode chuỗi tiếng Việt — mọi nhãn field lấy qua
   `apps.core.properties.label()`, mọi thông báo lỗi qua `.message()`.
2. KHÔNG hardcode `choices=[...]` — `ui_theme` để ModelForm tự lấy từ model,
   mà model lại lấy động từ MasterCode (`apps.core.constants`). Vì vậy thêm một
   lựa chọn mới chỉ cần thêm 1 dòng MasterCode, không phải sửa form này.

Ghi chú về HỌ TÊN: `AbstractUser.get_full_name()` ghép "first_name last_name"
theo thứ tự phương Tây, sai với tiếng Việt (Nguyễn Văn A). Nên toàn bộ họ tên
được lưu vào `first_name` (max_length 150, đủ dùng) và `last_name` để trống —
template hiển thị `user.first_name|default:user.username`.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from django import forms
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator

from apps.core.properties import label, message

User = get_user_model()

# Khoảng hợp lệ của "số từ ôn mỗi ngày" (SC08). Model chỉ là
# PositiveSmallIntegerField nên tự nó chấp nhận 0 và 32767 — cả hai đều vô
# nghĩa với người học và làm hỏng các con số trên trang chủ.
DAILY_GOAL_MIN = 1
DAILY_GOAL_MAX = 200

# Múi giờ cho SC08. ĐÂY LÀ NGOẠI LỆ CÓ CHỦ ĐÍCH với quy ước "không hardcode
# choices": múi giờ là danh sách chuẩn IANA, không phải danh mục nghiệp vụ do
# admin định nghĩa, nên không đưa vào MasterCode (xem claude/db-schema-django.md).
# Cố tình chỉ liệt kê những múi giờ người học Việt/Nhật thực sự dùng —
# zoneinfo.available_timezones() có hơn 600 mục, nhét hết vào một <select> thì
# không ai chọn nổi. Giá trị đang lưu của user luôn được thêm vào (xem
# `_timezone_choices`) nên dữ liệu cũ ngoài danh sách không bị mất khi lưu.
COMMON_TIMEZONES = [
    "Asia/Tokyo",
    "Asia/Ho_Chi_Minh",
    "Asia/Seoul",
    "Asia/Taipei",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Asia/Bangkok",
    "Australia/Sydney",
    "Europe/London",
    "America/Los_Angeles",
    "UTC",
]


def _timezone_choices(current=None):
    """Choices cho ô múi giờ, kèm độ lệch UTC để người dùng dễ nhận ra mình đang
    chọn đúng chưa ("Asia/Tokyo (UTC+09:00)").

    Độ lệch tính theo THỜI ĐIỂM HIỆN TẠI, cố ý: những vùng có giờ mùa hè
    (Europe/London, America/Los_Angeles) hiển thị đúng độ lệch đang áp dụng.
    Tên vùng lưu vào DB vẫn là tên IANA, không phải con số này.
    """
    names = list(COMMON_TIMEZONES)
    if current and current not in names:
        names.insert(0, current)

    choices = []
    for name in names:
        try:
            offset = datetime.now(ZoneInfo(name)).strftime("%z")
        except Exception:
            # Tên vùng lạ (dữ liệu cũ, nhập tay) thì bỏ qua thay vì làm vỡ cả
            # trang Cài đặt — ô select chỉ đơn giản không có sẵn mục đó.
            continue
        choices.append((name, f"{name} (UTC{offset[:3]}:{offset[3:]})"))
    return choices


def _required_message(*fields):
    """Gắn thông báo "bắt buộc nhập" dùng chung cho các field truyền vào."""
    for field in fields:
        field.error_messages["required"] = message("common.validation.required")


class LoginForm(forms.Form):
    """SC01_DangNhap.

    Ô đầu tiên nhận TÊN ĐĂNG NHẬP HOẶC EMAIL (đúng như nhãn
    `accounts.login.field.username`). Có ký tự "@" thì tra user theo email
    rồi mới `authenticate()` bằng username thật — không đổi AUTH backend,
    nên `ModelBackend` mặc định vẫn xử lý phần kiểm tra mật khẩu và
    `is_active`.

    Lưu ý: `AbstractUser.email` KHÔNG unique ở tầng model, trong khi
    `RegisterForm` lại chặn trùng. Dữ liệu cũ (import, createsuperuser) vẫn
    có thể trùng email, nên chỗ này lấy bản ghi có `pk` nhỏ nhất cho ổn
    định thay vì báo lỗi mơ hồ.
    """

    identifier = forms.CharField(max_length=254, strip=True)
    password = forms.CharField(strip=False, widget=forms.PasswordInput)

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)
        self.fields["identifier"].label = label("accounts.login.field.username")
        self.fields["password"].label = label("accounts.login.field.password")
        _required_message(*self.fields.values())

    def clean(self):
        cleaned = super().clean()
        identifier = cleaned.get("identifier")
        password = cleaned.get("password")
        if not identifier or not password:
            return cleaned

        username = identifier
        if "@" in identifier:
            match = User.objects.filter(email__iexact=identifier).order_by("pk").first()
            if match is not None:
                username = match.get_username()

        self.user = authenticate(self.request, username=username, password=password)
        if self.user is None:
            # Cùng một thông báo cho "sai user" và "sai mật khẩu" — không tiết
            # lộ tài khoản nào có tồn tại.
            raise ValidationError(message("accounts.login.error.invalid_credentials"))
        return cleaned

    def get_user(self):
        return self.user


class RegisterForm(forms.ModelForm):
    """SC02_DangKy."""

    full_name = forms.CharField(max_length=150, strip=True)
    password = forms.CharField(strip=False, widget=forms.PasswordInput)
    confirm_password = forms.CharField(strip=False, widget=forms.PasswordInput)

    field_order = ["full_name", "username", "email", "password", "confirm_password"]

    class Meta:
        model = User
        fields = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].label = label("accounts.register.field.fullname")
        self.fields["username"].label = label("accounts.register.field.username")
        self.fields["email"].label = label("accounts.register.field.email")
        self.fields["password"].label = label("accounts.register.field.password")
        self.fields["confirm_password"].label = label("common.field.confirm_password")
        # Email trên AbstractUser mặc định blank=True; màn đăng ký thì bắt buộc.
        self.fields["email"].required = True
        _required_message(*self.fields.values())

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(message("accounts.register.error.username_taken"))
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(message("accounts.register.error.email_taken"))
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        # Chạy đúng bộ AUTH_PASSWORD_VALIDATORS khai trong settings (độ dài tối
        # thiểu, mật khẩu phổ biến, toàn số...). Django có sẵn bản dịch tiếng
        # Việt cho các thông báo này nên không cần key riêng ở message.properties.
        password_validation.validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", message("common.validation.password_mismatch"))
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        # Xem ghi chú "HỌ TÊN" ở đầu file: giữ nguyên thứ tự tiếng Việt.
        user.first_name = self.cleaned_data["full_name"]
        user.last_name = ""
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    """SC09_ThongTinCaNhan."""

    full_name = forms.CharField(max_length=150, strip=True, required=False)

    field_order = ["full_name", "email"]

    class Meta:
        model = User
        fields = ["email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].label = label("common.field.fullname")
        self.fields["email"].label = label("common.field.email")
        if self.instance and self.instance.pk:
            self.fields["full_name"].initial = self.instance.first_name
        _required_message(*self.fields.values())

    def clean_email(self):
        email = self.cleaned_data["email"]
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError(message("accounts.register.error.email_taken"))
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data.get("full_name", "")
        if commit:
            user.save()
        return user


class SettingsForm(forms.ModelForm):
    """SC08_CaiDat — phần tuỳ chọn (giao diện, mục tiêu, múi giờ, thông báo).

    Đổi mật khẩu KHÔNG nằm ở form này, xem `PasswordUpdateForm` bên dưới: hai
    khu là hai <form> riêng POST về cùng một URL, phân biệt bằng ô ẩn `section`
    (xem apps.accounts.views.settings_view). Gộp chung thì gõ sai mật khẩu cũ
    sẽ kéo theo cả phần tuỳ chọn không lưu được, và ngược lại.

    `ui_theme` dùng RadioSelect thay cho <select> mặc định để template dựng
    được 3 thẻ có ô màu xem trước như mockup SC08. Choices vẫn lấy động từ
    MasterCode qua model — thêm một theme mới không phải sửa file này.
    """

    # Ngoại lệ "không hardcode choices" — xem ghi chú ở COMMON_TIMEZONES.
    timezone = forms.ChoiceField(choices=())

    class Meta:
        model = User
        fields = [
            "ui_theme",
            "daily_review_goal",
            "timezone",
            "daily_reminder_enabled",
            "weekly_email_summary_enabled",
        ]
        widgets = {"ui_theme": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ui_theme"].label = label("accounts.settings.section.theme")
        self.fields["daily_review_goal"].label = label(
            "accounts.settings.field.daily_review_goal"
        )
        self.fields["timezone"].label = label("accounts.settings.field.timezone")
        self.fields["timezone"].help_text = label("accounts.settings.hint.timezone")
        self.fields["daily_reminder_enabled"].label = label(
            "accounts.settings.field.daily_reminder"
        )
        self.fields["weekly_email_summary_enabled"].label = label(
            "accounts.settings.field.weekly_summary"
        )

        # Danh sách múi giờ dựng lúc chạy chứ không phải lúc import: giá trị
        # đang lưu của user phải luôn có mặt, và độ lệch UTC đổi theo giờ mùa hè.
        self.fields["timezone"].choices = _timezone_choices(
            getattr(self.instance, "timezone", None)
        )

        # `fields` của mỗi instance form là bản deepcopy riêng, nên append
        # validator ở đây không rò rỉ sang form khác.
        goal = self.fields["daily_review_goal"]
        goal_range = message(
            "accounts.settings.validation.goal_range",
            min=DAILY_GOAL_MIN, max=DAILY_GOAL_MAX,
        )
        goal.validators.append(MinValueValidator(DAILY_GOAL_MIN, message=goal_range))
        goal.validators.append(MaxValueValidator(DAILY_GOAL_MAX, message=goal_range))
        goal.widget.attrs.update({"min": DAILY_GOAL_MIN, "max": DAILY_GOAL_MAX})

        _required_message(*self.fields.values())


class PasswordUpdateForm(PasswordChangeForm):
    """SC08_CaiDat — khu "Đổi mật khẩu".

    Kế thừa `PasswordChangeForm` của Django để dùng lại đúng phần đã được kiểm
    chứng: xác minh mật khẩu HIỆN TẠI (chặn người ngồi vào máy đang mở sẵn phiên
    đăng nhập đổi mật khẩu), chạy đủ AUTH_PASSWORD_VALIDATORS, so khớp hai lần
    nhập. Ở đây chỉ thay nhãn để không hardcode chuỗi tiếng Việt.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = label(
            "accounts.settings.field.current_password"
        )
        self.fields["new_password1"].label = label(
            "accounts.settings.field.new_password"
        )
        self.fields["new_password2"].label = label("common.field.confirm_password")
        # help_text mặc định của new_password1 là một khối <ul> do
        # password_validators_help_text_html() sinh ra; partials/field.html bọc
        # help_text trong <p> nên sẽ thành <ul> lồng trong <p>. Bỏ đi, quy tắc
        # nào vi phạm thì đã hiện thành thông báo lỗi ngay dưới ô nhập.
        for field in self.fields.values():
            field.help_text = ""
        _required_message(*self.fields.values())
