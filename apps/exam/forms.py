"""
Form S2 — Tạo bài kiểm tra từ vựng (htmlTemplate/SC23_KiemTra_A.html màn S2).

forms.Form chứ không ModelForm: một lượt (ExamAttempt) do service dựng từ các
lựa chọn này, người dùng không gõ thẳng vào cột nào của model.
"""
from django import forms

from apps.core.constants import VOCAB_QUESTION_TYPES, VOCAB_Q_MEANING, VOCAB_Q_READING, VOCAB_Q_WORD
from apps.core.properties import message

from .constants import SCOPE_DUE, SCOPE_TOPICS, VOCAB_COUNTS, VOCAB_DEFAULT_COUNT, VOCAB_SCOPES


class VocabSetupForm(forms.Form):
    scope = forms.ChoiceField(choices=[(s, s) for s in VOCAB_SCOPES], initial=SCOPE_DUE)
    topics = forms.MultipleChoiceField(required=False)
    types = forms.MultipleChoiceField(
        choices=[(t, t) for t in VOCAB_QUESTION_TYPES],
        initial=[VOCAB_Q_MEANING, VOCAB_Q_WORD, VOCAB_Q_READING],
        required=False,
    )
    count = forms.TypedChoiceField(choices=[(n, n) for n in VOCAB_COUNTS], coerce=int,
                                   initial=VOCAB_DEFAULT_COUNT)
    srs_link = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, topics=(), **kwargs):
        super().__init__(*args, **kwargs)
        # Chủ đề do view truyền vào (chỉ chủ đề người học đã học đủ từ), không
        # cho POST id chủ đề bất kỳ.
        self.fields["topics"].choices = [(str(t.pk), t.display_name) for t in topics]

    def clean(self):
        data = super().clean()
        if not data.get("types"):
            self.add_error("types", message("exam.vocab.validation.types_required"))
        if data.get("scope") == SCOPE_TOPICS and not data.get("topics"):
            self.add_error("topics", message("exam.vocab.validation.topics_required"))
        return data
