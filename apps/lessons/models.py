"""
Học theo bài — giáo trình hội thoại công sở "Quyển 1" (12 chương, 45 bài) lấy từ bjt.db
của BJT-WEB. Spec: docs/SPEC_LUYEN_TAP_BAI.md.

Đợt này (phần 2) chỉ có khung bài + ba dạng luyện tập:
  - Drill / DrillItem          : luyện thay thế — câu mẫu + 3 gợi ý
  - Roleplay / Line / Blank    : hội thoại đóng vai — lời thoại có chỗ trống {1} {2}
  - PolitenessPhrase           : câu gắn mức lịch sự (MasterCode 25)
Phần 1 (hội thoại đầy đủ, audio, câu then chốt) thêm vào CÙNG app sau, không đổi khoá.

Khoá tự nhiên của dataio (màn nhập SC07b) suy từ UniqueConstraint / unique của từng model —
đổi chúng là đổi header file CSV ở docs/data/lessons/.
"""
from django.conf import settings
from django.db import models

from apps.core.constants import politeness_level_choices, practice_kind_choices
from apps.core.models import AuditableModel


class Unit(AuditableModel):
    """Một chương (12 chương, vd 'Giới thiệu', 'Bày tỏ ý định')."""

    number = models.PositiveSmallIntegerField(unique=True)
    name_jp = models.CharField(max_length=60)
    name_vi = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["number"]
        verbose_name = "Chương (Quyển 1)"
        verbose_name_plural = "Chương (Quyển 1)"

    def __str__(self):
        return f"{self.number}. {self.name_vi or self.name_jp}"


class Lesson(AuditableModel):
    """Một bài (= 'scene' trong sách, đánh số 1-45 xuyên chương)."""

    unit = models.ForeignKey(Unit, related_name="lessons", on_delete=models.PROTECT)
    scene_no = models.PositiveSmallIntegerField(unique=True)
    title_jp = models.CharField(max_length=100)
    title_vi = models.CharField(max_length=150, blank=True)
    situation_vi = models.TextField(blank=True)

    class Meta:
        ordering = ["scene_no"]
        verbose_name = "Bài (Quyển 1)"
        verbose_name_plural = "Bài (Quyển 1)"

    def __str__(self):
        return f"{self.scene_no}. {self.title_jp}"


class Drill(AuditableModel):
    """Bài luyện thay thế — mỗi bài tối đa MỘT (34/45 bài có)."""

    lesson = models.OneToOneField(Lesson, related_name="drill", on_delete=models.CASCADE)
    example_prompt_jp = models.CharField(max_length=200, help_text="Vế trái câu mẫu, vd 山川物産、佐藤課長")
    example_answer_jp = models.CharField(max_length=300)

    class Meta:
        ordering = ["lesson__scene_no"]
        verbose_name = "Luyện thay thế"
        verbose_name_plural = "Luyện thay thế"

    def __str__(self):
        return f"Drill {self.lesson.scene_no}"


class DrillItem(AuditableModel):
    drill = models.ForeignKey(Drill, related_name="items", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    prompt_jp = models.CharField(max_length=200)
    answer_jp = models.CharField(max_length=300)

    class Meta:
        ordering = ["drill_id", "number"]
        constraints = [models.UniqueConstraint(fields=["drill", "number"], name="uniq_lessons_drill_item")]
        verbose_name = "Câu luyện thay thế"
        verbose_name_plural = "Câu luyện thay thế"

    def __str__(self):
        return self.prompt_jp


class Roleplay(AuditableModel):
    """Hội thoại đóng vai (復習) — 2 đoạn mỗi chương."""

    unit = models.ForeignKey(Unit, related_name="roleplays", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    situation_vi = models.TextField()
    book_page = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["unit__number", "number"]
        constraints = [models.UniqueConstraint(fields=["unit", "number"], name="uniq_lessons_roleplay")]
        verbose_name = "Hội thoại đóng vai"
        verbose_name_plural = "Hội thoại đóng vai"

    def __str__(self):
        return f"Chương {self.unit.number} - đóng vai {self.number}"


class RoleplayLine(AuditableModel):
    roleplay = models.ForeignKey(Roleplay, related_name="lines", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    speaker = models.CharField(max_length=40)
    text_jp = models.CharField(max_length=300, help_text="Chỗ trống ghi {1}, {2}... khớp RoleplayBlank.number")

    class Meta:
        ordering = ["roleplay_id", "number"]
        constraints = [models.UniqueConstraint(fields=["roleplay", "number"], name="uniq_lessons_roleplay_line")]
        verbose_name = "Lời thoại đóng vai"
        verbose_name_plural = "Lời thoại đóng vai"

    def __str__(self):
        return self.text_jp[:60]


class RoleplayBlank(AuditableModel):
    roleplay = models.ForeignKey(Roleplay, related_name="blanks", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    answer_jp = models.CharField(max_length=200)

    class Meta:
        ordering = ["roleplay_id", "number"]
        constraints = [models.UniqueConstraint(fields=["roleplay", "number"], name="uniq_lessons_roleplay_blank")]
        verbose_name = "Đáp án chỗ trống"
        verbose_name_plural = "Đáp án chỗ trống"

    def __str__(self):
        return f"{{{self.number}}} {self.answer_jp}"


class PolitenessPhrase(AuditableModel):
    lesson = models.ForeignKey(Lesson, related_name="politeness_phrases", on_delete=models.CASCADE)
    phrase_jp = models.CharField(max_length=200)
    level_code = models.CharField(max_length=10, choices=politeness_level_choices)

    class Meta:
        ordering = ["lesson__scene_no", "level_code"]
        constraints = [models.UniqueConstraint(fields=["lesson", "phrase_jp"], name="uniq_lessons_politeness")]
        verbose_name = "Câu theo mức lịch sự"
        verbose_name_plural = "Câu theo mức lịch sự"

    def __str__(self):
        return self.phrase_jp


class UserPracticeMark(AuditableModel):
    """Kết quả GẦN NHẤT của một người với một câu luyện tập (spec ◆3) — không lưu từng lượt.

    `kind` + `object_id` thay vì 3 FK: ba dạng cùng một nhu cầu và màn tổng quan đếm cả
    ba trong một truy vấn.
    shortcut: không có FK nên xoá câu không xoá dấu của nó; nhập lại bằng upsert giữ nguyên
    id nên không sao — nếu sau này xoá/nạp lại sạch thì dọn dấu mồ côi theo kind.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="practice_marks", on_delete=models.CASCADE)
    kind = models.CharField(max_length=10, choices=practice_kind_choices)
    object_id = models.PositiveBigIntegerField()
    is_known = models.BooleanField(default=False)
    times = models.PositiveIntegerField(default=0)
    last_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "kind", "object_id"], name="uniq_lessons_practice_mark"),
        ]
        verbose_name = "Kết quả luyện tập"
        verbose_name_plural = "Kết quả luyện tập"

    def __str__(self):
        return f"{self.user_id}:{self.kind}:{self.object_id}"
