"""Form của khu quản trị (SC07)."""
from django import forms

from apps.core.constants import keepalive_interval_choices
from apps.core.models import SiteSetting
from apps.core.properties import label, message


class SiteSettingForm(forms.ModelForm):
    """Màn Cài đặt hệ thống — hiện chỉ có nhóm tự ping giữ server thức.

    Dropdown chu kỳ lấy từ MasterCode code_type 17 (không hardcode choices),
    nạp trong __init__ để admin thêm mã mới là dropdown có ngay, không cần
    khởi động lại tiến trình."""

    keepalive_interval_code = forms.ChoiceField(choices=())

    class Meta:
        model = SiteSetting
        fields = ["keepalive_enabled", "keepalive_interval_code"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["keepalive_enabled"].required = False
        self.fields["keepalive_enabled"].label = label("admin.system.field.keepalive_enabled")
        field = self.fields["keepalive_interval_code"]
        field.label = label("admin.system.field.keepalive_interval")
        field.choices = keepalive_interval_choices()

    def clean_keepalive_interval_code(self):
        code = self.cleaned_data["keepalive_interval_code"]
        try:
            minutes = int(code)
        except (TypeError, ValueError):
            minutes = 0
        # Mã MasterCode do admin tự thêm cũng phải < 15 phút, nếu không server
        # ngủ trước khi kịp ping lần sau.
        if not 1 <= minutes < 15:
            raise forms.ValidationError(message("admin.system.error.invalid_interval"))
        return code
