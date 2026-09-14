"""
Form tuỳ chọn phiếu PDF (SC10).

Đây là `forms.Form` chứ không phải ModelForm: một nửa dữ liệu của
`PracticeSheet` (danh sách từ, file PDF, custom_words) do view dựng chứ không
do người dùng gõ, nên ModelForm sẽ phải `exclude` gần hết rồi vẫn tự set tay.
"""
from django import forms

from apps.core.constants import (
    RECALL_JP_TO_VI,
    RECALL_MIXED,
    RECALL_VI_TO_JP,
    SHEET_TYPE_RECALL,
    SHEET_TYPE_WRITING,
    sheet_type_choices,
)
from apps.core.properties import message

LINES_MIN = 1
LINES_MAX = 5

SOURCE_EXISTING = "existing"
SOURCE_UPLOAD = "upload"
SOURCE_CHOICES = ((SOURCE_EXISTING, "existing"), (SOURCE_UPLOAD, "upload"))


class PracticeSheetForm(forms.Form):
    source = forms.ChoiceField(choices=SOURCE_CHOICES, initial=SOURCE_EXISTING)
    sheet_type = forms.ChoiceField(widget=forms.RadioSelect)

    # Phiếu luyện viết
    lines_per_word = forms.IntegerField(
        min_value=LINES_MIN, max_value=LINES_MAX, initial=2, required=False,
    )
    show_guide_character = forms.BooleanField(required=False, initial=True)
    show_reading_and_meaning = forms.BooleanField(required=False, initial=True)

    # Phiếu ôn lại từ.
    #
    # Hai HƯỚNG là hai ô tick độc lập chứ không phải một ô radio ba trạng thái
    # (quyết định của Dat 14/09): tick cả hai nghĩa là trộn. Người dùng nghĩ
    # theo kiểu "phiếu này có phần JP→VN, có phần VN→JP, có đáp án" chứ không
    # nghĩ theo kiểu "chọn một trong ba chế độ". DB vẫn lưu một chuỗi
    # jp_vi/vi_jp/mixed như cũ — quy đổi ở `sheet_options`, không cần migration.
    direction_jp_vi = forms.BooleanField(required=False, initial=True)
    direction_vi_jp = forms.BooleanField(required=False, initial=False)
    include_answer_key = forms.BooleanField(required=False, initial=True)

    include_sentence_box = forms.BooleanField(required=False, initial=True)
    shuffle_order = forms.BooleanField(required=False, initial=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Nạp choices trong __init__, KHÔNG ở cấp lớp: get_choices() truy vấn
        # MasterCode, mà thân lớp chạy lúc import module — trên DB trống (lần
        # migrate đầu của Supabase) truy vấn đó nổ và kéo theo cả site.
        self.fields["sheet_type"].choices = sheet_type_choices()
        self.fields["sheet_type"].initial = SHEET_TYPE_WRITING

    def clean_lines_per_word(self):
        # Ô này chỉ hiện với phiếu luyện viết nên có thể trống; model có default.
        return self.cleaned_data.get("lines_per_word") or 2

    def clean(self):
        data = super().clean()
        if data.get("sheet_type") == SHEET_TYPE_RECALL and not self._direction_code(data):
            # Chỉ tick "Answer" mà không tick hướng nào thì in ra đúng một trang
            # đáp án, không có chỗ trống nào để làm bài — gần như chắc chắn là
            # quên tick chứ không phải cố ý, nên báo ngay thay vì in bừa.
            self.add_error(None, message("practice_sheets.validation.direction_required"))
        return data

    @staticmethod
    def _direction_code(data):
        """Hai ô tick -> một mã cho DB. Không tick ô nào -> chuỗi rỗng."""
        jp = bool(data.get("direction_jp_vi"))
        vi = bool(data.get("direction_vi_jp"))
        if jp and vi:
            return RECALL_MIXED
        if jp:
            return RECALL_JP_TO_VI
        if vi:
            return RECALL_VI_TO_JP
        return ""

    @property
    def sheet_options(self):
        """Tuỳ chọn để truyền thẳng vào generate_sheet_pdf()."""
        data = self.cleaned_data
        return {
            "lines_per_word": data.get("lines_per_word") or 2,
            "show_guide_character": bool(data.get("show_guide_character")),
            "show_reading_and_meaning": bool(data.get("show_reading_and_meaning")),
            "recall_direction": self._direction_code(data),
            "include_sentence_box": bool(data.get("include_sentence_box")),
            "include_answer_key": bool(data.get("include_answer_key")),
            "shuffle_order": bool(data.get("shuffle_order")),
        }
