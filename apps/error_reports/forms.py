"""
Form người dùng gửi báo lỗi (SC14) và form admin xử lý.

ModelForm (khác PracticeSheetForm bên SC10): ở đây người dùng gõ gần như toàn
bộ field được lưu, nên ModelForm là đúng chỗ — không phải exclude gần hết.
"""
from django import forms

from apps.core.constants import error_type_choices
from apps.core.properties import label, message

from .models import ErrorReport

DESCRIPTION_MIN_LENGTH = 10


class ErrorReportForm(forms.ModelForm):
    """Người học báo một lỗi. `vocabulary` do view gán, không cho sửa trên form
    (link "🚩 Báo lỗi" đã mang sẵn id từ vựng)."""

    class Meta:
        model = ErrorReport
        fields = ["error_type_code", "description", "suggested_fix"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Nạp choices trong __init__ chứ KHÔNG ở cấp lớp: get_choices() query
        # MasterCode, mà thân lớp chạy lúc import module — trên DB trống (lần
        # migrate đầu) truy vấn đó nổ và kéo theo cả site. Cùng lý do với
        # apps/practice_sheets/forms.py.
        self.fields["error_type_code"] = forms.ChoiceField(
            choices=error_type_choices(),
            label=label("error_report.form.field.error_type"),
        )
        self.fields["description"].label = label("error_report.form.field.description")
        self.fields["suggested_fix"].label = label("error_report.form.field.suggested_fix")
        self.fields["suggested_fix"].required = False

    def clean_description(self):
        text = (self.cleaned_data.get("description") or "").strip()
        if len(text) < DESCRIPTION_MIN_LENGTH:
            # "sai" / "lỗi" không đủ để admin biết phải sửa gì.
            raise forms.ValidationError(
                message("error_report.validation.description_too_short", min=DESCRIPTION_MIN_LENGTH)
            )
        return text


class ErrorReportActionForm(forms.Form):
    """Form admin bấm ở màn Báo cáo lỗi. `action` quyết định gọi service nào —
    xem apps/error_reports/services.py."""

    ACTION_FIX = "fix"
    ACTION_DISMISS = "dismiss"
    ACTION_REOPEN = "reopen"
    ACTION_CHOICES = (
        (ACTION_FIX, ACTION_FIX),
        (ACTION_DISMISS, ACTION_DISMISS),
        (ACTION_REOPEN, ACTION_REOPEN),
    )

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    admin_response = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
