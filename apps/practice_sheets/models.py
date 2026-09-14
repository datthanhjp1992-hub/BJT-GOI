"""
Stores a record of each practice PDF a user generated (SC10), so they can
re-download it later instead of regenerating from scratch.

Hai loại phiếu (14/09/2026), phân biệt bằng `sheet_type`:
- `writing` — ô vuông kiểu genkoyoshi để tập viết tay.
- `recall`  — liệt kê từ và chừa chỗ trống để tự viết lại nghĩa / cách đọc /
  đặt câu; `recall_direction` quyết định vế nào được cho sẵn.
"""
from django.conf import settings
from django.db import models

from apps.core.constants import (
    SHEET_TYPE_WRITING,
    recall_direction_choices,
    sheet_type_choices,
)
from apps.core.models import AuditableModel
from apps.vocabulary.models import Vocabulary


class PracticeSheet(AuditableModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="practice_sheets", on_delete=models.CASCADE)

    # Từ vựng CÓ trong hệ thống. Danh sách tải lên từ file mà chưa có trong DB
    # thì nằm ở custom_words bên dưới — xem ghi chú ở đó.
    words = models.ManyToManyField(
        Vocabulary, related_name="practice_sheets",
        through="practice_sheets.PracticeSheetWord",
    )

    sheet_type = models.CharField(
        max_length=20, choices=sheet_type_choices, default=SHEET_TYPE_WRITING,
        help_text="MasterCode code_type '10'.",
    )

    # --- Tuỳ chọn của phiếu LUYỆN VIẾT ---
    lines_per_word = models.PositiveSmallIntegerField(default=2)
    show_guide_character = models.BooleanField(default=True)
    show_reading_and_meaning = models.BooleanField(default=True)

    # --- Tuỳ chọn của phiếu ÔN LẠI TỪ ---
    recall_direction = models.CharField(
        max_length=20, choices=recall_direction_choices, blank=True,
        help_text="MasterCode code_type '11'. Để trống với phiếu luyện viết.",
    )
    include_sentence_box = models.BooleanField(
        default=True, help_text="Chừa thêm một dòng kẻ để tự đặt câu với từ đó.",
    )
    include_answer_key = models.BooleanField(
        default=True, help_text="Thêm trang đáp án ở cuối để tự chấm.",
    )
    shuffle_order = models.BooleanField(
        default=False, help_text="Xáo trộn thứ tự để in lại cùng danh sách mà không thuộc lòng theo vị trí.",
    )

    pdf_file = models.FileField(upload_to="practice_sheets/")

    # Danh sách từ tải lên từ file mà KHÔNG có trong bảng Vocabulary.
    #
    # Quyết định của Dat (14/09/2026): người học phải in được phiếu từ file của
    # riêng mình mà không cần quyền admin và không làm bẩn từ điển chung. M2M
    # `words` chỉ trỏ được tới Vocabulary nên những từ đó lưu ở đây, dạng
    # [{"word": ..., "reading": ..., "meaning_vi": ...}, ...].
    #
    # editable=False là CỐ Ý: field này do view điền, không phải admin gõ tay.
    # Nhờ vậy nó cũng tự bị loại khỏi file mẫu CSV/Excel của SC07b
    # (apps/core/dataio.py bỏ mọi field không editable) — một cột JSON trong
    # file Excel thì không ai điền nổi.
    custom_words = models.JSONField(default=list, blank=True, editable=False)

    def __str__(self):
        return f"PracticeSheet #{self.pk} ({self.user})"

    def word_items(self):
        """Danh sách từ của phiếu, gộp cả hai nguồn, để vẽ lại PDF.

        Import trong thân hàm: wordsource nằm cùng app nhưng import ở đầu file
        sẽ thành vòng (wordsource không cần models, nhưng giữ chiều phụ thuộc
        một chiều cho chắc).
        """
        from .wordsource import WordItem

        items = [WordItem.from_vocabulary(link.vocabulary) for link in
                 self.word_links.select_related("vocabulary").order_by("pk")]
        items += [WordItem.from_dict(d) for d in (self.custom_words or [])]
        return items


class PracticeSheetWord(AuditableModel):
    """Bảng nối PracticeSheet <-> Vocabulary, khai tường minh để có đủ 4 cột audit.

    Xem ghi chú ở apps.vocabulary.models.VocabularyTopic về .add() và created_by.
    """

    sheet = models.ForeignKey(PracticeSheet, related_name="word_links", on_delete=models.CASCADE)
    vocabulary = models.ForeignKey(Vocabulary, related_name="practice_sheet_links", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("sheet", "vocabulary")
        verbose_name = "PracticeSheet-Vocabulary link"

    def __str__(self):
        return f"{self.sheet_id} - {self.vocabulary_id}"
