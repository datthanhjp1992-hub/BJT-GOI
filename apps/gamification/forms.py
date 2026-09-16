"""
Form màn SC11 — Góp ý từ vựng.

BA form riêng thay vì một form khổng lồ có `required` động: mỗi loại góp ý có
bộ field bắt buộc khác hẳn nhau, gộp lại thì `clean()` sẽ đầy `if type == ...`
và thông báo lỗi khó chính xác. Người dùng chọn loại bằng LINK (`?type=`) nên
mỗi lượt render chỉ có đúng một form trên trang.

Lưu ý về `comment_text`: field này trong model mang HAI vai trò tuỳ loại góp ý
— với "Bình luận" là nội dung công khai sau khi duyệt; với "Từ mới"/"Sửa nghĩa"
là ghi chú/lý do người gửi viết cho admin đọc (mockup gọi là "Ghi chú thêm" và
"Lý do đề xuất"). Không tách field mới vì cả hai đều là văn bản tự do của người
gửi, và tách sẽ phải migrate một bảng đang có dữ liệu.
"""
from django import forms

from apps.core.properties import label, message
from apps.vocabulary.models import Topic, Vocabulary

COMMENT_MIN_LENGTH = 5


def _vocabulary_queryset():
    """Danh sách từ cho ô chọn.

    Chấp nhận nạp cả bảng như mockup vẽ: người dùng thường vào màn này qua link
    "Góp ý sửa" ở flashcard/SC05 (đã mang sẵn `?vocabulary=<id>`), ô chọn chỉ là
    lối vào phụ. Khi kho từ lớn tới mức <select> nặng thì đổi sang ô tìm kiếm,
    không phải sửa gì khác trong form.
    """
    return Vocabulary.objects.order_by("word")


class _VocabularyChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.word} — {obj.reading} ({obj.meaning_vi})"


class NewWordForm(forms.Form):
    """Đề xuất một từ CHƯA có trong hệ thống."""

    word = forms.CharField(max_length=100)
    reading = forms.CharField(max_length=150)
    meaning_vi = forms.CharField(max_length=255)
    topic = forms.ModelChoiceField(queryset=Topic.objects.none(), required=False)
    note = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, locked_vocabulary=None, **kwargs):
        # "Từ mới" không gắn với từ nào sẵn có nên KHÔNG dùng locked_vocabulary
        # — vẫn nhận tham số để view gọi cả ba form theo cùng một cách.
        super().__init__(*args, **kwargs)
        # Nạp queryset trong __init__, không ở cấp lớp: thân lớp chạy lúc import
        # module, trên DB trống (lần migrate đầu) truy vấn đó nổ. Cùng lý do với
        # apps/practice_sheets/forms.py.
        self.fields["topic"].queryset = Topic.objects.all()
        self.fields["word"].label = label("contribution.form.field.word")
        self.fields["reading"].label = label("contribution.form.field.reading")
        self.fields["meaning_vi"].label = label("contribution.form.field.meaning_vi")
        self.fields["topic"].label = label("contribution.form.field.topic")
        self.fields["note"].label = label("contribution.form.field.extra_note")

    def clean_word(self):
        word = (self.cleaned_data.get("word") or "").strip()
        # Trùng từ đã có thì đây là góp ý "Sửa nghĩa" chứ không phải "Từ mới" —
        # chặn ngay lúc gửi, đỡ để admin phải từ chối thủ công.
        if Vocabulary.objects.filter(word__iexact=word).exists():
            raise forms.ValidationError(message("contribution.submit.error.duplicate_word"))
        return word

    def as_contribution_fields(self):
        data = self.cleaned_data
        return {
            "proposed_word": data["word"],
            "proposed_reading": data["reading"].strip(),
            "proposed_meaning_vi": data["meaning_vi"].strip(),
            "proposed_topic": data.get("topic"),
            "comment_text": (data.get("note") or "").strip(),
        }


class _TargetedForm(forms.Form):
    """Phần dùng chung cho 2 loại góp ý có gắn với một từ đã có.

    `locked_vocabulary` = vào màn này từ link "Góp ý" ở flashcard/SC05, tức là
    người dùng đang nói về ĐÚNG từ đó. Khi đó ô chọn từ bị KHOÁ: queryset thu
    còn đúng một bản ghi (đổi id trên form cũng không qua được validate) và
    widget đổi sang hidden — template hiện tên từ dưới dạng chữ, không phải
    <select>. Muốn góp ý cho từ khác thì vào màn Góp ý từ thanh menu.
    """

    def _setup_target(self, locked_vocabulary):
        field = self.fields["target_vocabulary"]
        field.label = label("contribution.form.field.target_word")
        if locked_vocabulary is not None:
            field.queryset = Vocabulary.objects.filter(pk=locked_vocabulary.pk)
            field.widget = forms.HiddenInput()
            field.initial = locked_vocabulary
        else:
            field.queryset = _vocabulary_queryset()


class EditMeaningForm(_TargetedForm):
    """Đề xuất sửa nghĩa / cách đọc của một từ đã có."""

    target_vocabulary = _VocabularyChoiceField(queryset=Vocabulary.objects.none())
    proposed_meaning_vi = forms.CharField(max_length=255)
    proposed_reading = forms.CharField(max_length=150, required=False)
    reason = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, locked_vocabulary=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_target(locked_vocabulary)
        self.fields["proposed_meaning_vi"].label = label("contribution.form.field.proposed_meaning")
        self.fields["proposed_reading"].label = label("contribution.form.field.reading")
        self.fields["reason"].label = label("contribution.form.field.reason")

    def as_contribution_fields(self):
        data = self.cleaned_data
        return {
            "target_vocabulary": data["target_vocabulary"],
            "proposed_meaning_vi": data["proposed_meaning_vi"].strip(),
            "proposed_reading": (data.get("proposed_reading") or "").strip(),
            "comment_text": (data.get("reason") or "").strip(),
        }


class CommentForm(_TargetedForm):
    """Bình luận công khai dưới một từ (hiện sau khi admin duyệt)."""

    target_vocabulary = _VocabularyChoiceField(queryset=Vocabulary.objects.none())
    comment_text = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, locked_vocabulary=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_target(locked_vocabulary)
        self.fields["comment_text"].label = label("contribution.form.field.comment_text")

    def clean_comment_text(self):
        text = (self.cleaned_data.get("comment_text") or "").strip()
        if len(text) < COMMENT_MIN_LENGTH:
            raise forms.ValidationError(
                message("contribution.validation.comment_too_short", min=COMMENT_MIN_LENGTH)
            )
        return text

    def as_contribution_fields(self):
        data = self.cleaned_data
        return {
            "target_vocabulary": data["target_vocabulary"],
            "comment_text": data["comment_text"],
        }


class ContributionActionForm(forms.Form):
    """Form admin bấm ở hòm thư SC12 — `action` quyết định gọi service nào."""

    ACTION_APPROVE = "approve"
    ACTION_REJECT = "reject"
    ACTION_CHOICES = ((ACTION_APPROVE, ACTION_APPROVE), (ACTION_REJECT, ACTION_REJECT))

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    admin_response = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    # Admin được sửa lại nội dung đề xuất TRƯỚC khi duyệt (mockup SC12 vẽ các ô
    # này ở cột phải): dữ liệu ghi vào Vocabulary sẽ theo đúng các ô dưới đây.
    word = forms.CharField(max_length=100, required=False)
    reading = forms.CharField(max_length=150, required=False)
    meaning_vi = forms.CharField(max_length=255, required=False)
    topic = forms.ModelChoiceField(queryset=Topic.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topic"].queryset = Topic.objects.all()
