"""
Stores a record of each handwriting-practice PDF a user generated (SC10),
so they can re-download it later instead of regenerating from scratch.
"""
from django.conf import settings
from django.db import models

from apps.core.models import AuditableModel
from apps.vocabulary.models import Vocabulary


class PracticeSheet(AuditableModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="practice_sheets", on_delete=models.CASCADE)
    words = models.ManyToManyField(
        Vocabulary, related_name="practice_sheets",
        through="practice_sheets.PracticeSheetWord",
    )
    lines_per_word = models.PositiveSmallIntegerField(default=2)
    show_guide_character = models.BooleanField(default=True)
    show_reading_and_meaning = models.BooleanField(default=True)
    pdf_file = models.FileField(upload_to="practice_sheets/")

    def __str__(self):
        return f"PracticeSheet #{self.pk} ({self.user})"


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
