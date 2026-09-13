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
from django import forms
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.core.exceptions import ValidationError

from apps.core.properties import label, message

User = get_user_model()


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
    """SC08_CaiDat."""

    class Meta:
        model = User
        fields = [
            "ui_theme",
            "daily_review_goal",
            "daily_reminder_enabled",
            "weekly_email_summary_enabled",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ui_theme"].label = label("accounts.settings.section.theme")
        self.fields["daily_review_goal"].label = label(
            "accounts.settings.field.daily_review_goal"
        )
        self.fields["daily_reminder_enabled"].label = label(
            "accounts.settings.field.daily_reminder"
        )
        self.fields["weekly_email_summary_enabled"].label = label(
            "accounts.settings.field.weekly_summary"
        )
        _required_message(*self.fields.values())
