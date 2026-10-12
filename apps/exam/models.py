"""
Khu Kiểm tra — docs/SPEC_KIEM_TRA.md mục 1.2. Mockup: htmlTemplate/SC23_KiemTra_A.html.

Bốn loại bài dùng chung MỘT cặp ExamAttempt / ExamAnswer:
  - vocab     : câu sinh từ Vocabulary lúc bắt đầu, ảnh chụp câu nằm ở ExamAnswer.payload
  - drill/mock: câu tham chiếu ExamQuestion (nhập từ mock_exam_question của bjt.db)
  - wrongbook : ôn lại WrongBookEntry

Mọi model kế thừa AuditableModel; mọi danh sách lựa chọn đi qua MasterCode
(code_type 20-23, apps/core/constants.py).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.constants import (
    exam_kind_choices,
    exam_mode_choices,
    exam_section_choices,
    vocab_question_choices,
)
from apps.core.models import AuditableModel
from apps.vocabulary.models import Vocabulary


class ExamSet(AuditableModel):
    """Một bộ đề thi thử (bjt.db có 5 bộ × 100 câu)."""

    number = models.PositiveSmallIntegerField(unique=True)
    title = models.CharField(max_length=80, help_text="vd 'Bộ đề 1'")
    slug = models.SlugField(max_length=40, unique=True)
    is_active = models.BooleanField(default=True)
    source_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["number"]
        verbose_name = "Bộ đề thi thử"
        verbose_name_plural = "Bộ đề thi thử"

    def __str__(self):
        return self.title


class ExamQuestion(AuditableModel):
    """Một câu đề BJT.

    passage_jp mang hai nghĩa theo phần đề:
      - phần Nghe, câu hội thoại: LỜI THOẠI — ẩn tới khi người học được xem đáp án;
      - 場面設定 và phần Đọc / Nghe + Đọc: văn bản hiện cùng câu hỏi.
    """

    exam_set = models.ForeignKey(ExamSet, related_name="questions", on_delete=models.CASCADE)
    part = models.PositiveSmallIntegerField(help_text="1 = Nghe, 2 = Nghe + Đọc, 3 = Đọc")
    section_code = models.CharField(max_length=10, choices=exam_section_choices)
    number = models.PositiveSmallIntegerField(help_text="Thứ tự trong bộ đề, 1..100")
    passage_type = models.CharField(max_length=40, blank=True, help_text="会話 / 社内文書 / スケジュール表 ...")
    passage_jp = models.TextField(blank=True)
    stem_jp = models.TextField()
    audio_path = models.CharField(
        max_length=120, blank=True,
        help_text="Đường dẫn trong bucket exam-audio, vd mock/q031_part1_sec1.mp3 — URL dựng ở exam_audio_url().",
    )
    # Tăng mỗi lần scripts/upload_exam_audio.py ghi đè file -> URL đổi ?v= -> CDN và
    # trình duyệt tải bản mới ngay (spec mục 0.3).
    audio_version = models.PositiveIntegerField(default=1)
    explanation_vi = models.TextField(blank=True)
    level = models.CharField(max_length=10, blank=True, help_text="N1/N2/N3 theo nguồn")
    source_ref = models.CharField(max_length=60, unique=True, help_text="vd bjt.db:mock_exam_question:31")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["exam_set", "number"]
        constraints = [
            models.UniqueConstraint(fields=["exam_set", "number"], name="uniq_exam_question_number"),
        ]
        indexes = [models.Index(fields=["section_code", "is_active"])]
        verbose_name = "Câu đề thi"
        verbose_name_plural = "Câu đề thi"

    def __str__(self):
        return f"{self.exam_set_id}-{self.number}"

    @property
    def passage_is_transcript(self):
        """passage_jp là LỜI THOẠI của bài nghe (ẩn tới khi được xem đáp án)?

        Câu có audio mà passage không phải 場面設定 (đề bài tình huống in sẵn) thì
        passage chính là lời thoại. Phần Đọc / tài liệu: passage là văn bản đề bài."""
        return bool(self.audio_path) and self.passage_type != SCENE_PASSAGE_TYPE


# Câu kính ngữ phần Nghe in sẵn tình huống — hiện cùng câu hỏi, không phải lời thoại.
SCENE_PASSAGE_TYPE = "場面設定"


class ExamOption(AuditableModel):
    question = models.ForeignKey(ExamQuestion, related_name="options", on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField(help_text="1..4, giữ đúng thứ tự đề gốc")
    text_jp = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["question", "position"]
        constraints = [
            models.UniqueConstraint(fields=["question", "position"], name="uniq_exam_option_position"),
        ]
        verbose_name = "Phương án"
        verbose_name_plural = "Phương án"

    def __str__(self):
        return f"{self.position}. {self.text_jp}"

    def clean(self):
        """Mỗi câu đúng MỘT phương án đúng — giống keigo.QuestionOption."""
        if not self.is_correct or not self.question_id:
            return
        others = ExamOption.objects.filter(question_id=self.question_id, is_correct=True).exclude(pk=self.pk)
        if others.exists():
            raise ValidationError({"is_correct": "Câu này đã có một phương án đúng khác."})


class ExamAttempt(AuditableModel):
    """Một lượt làm bài. finished_at rỗng = đang làm dở."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="exam_attempts", on_delete=models.CASCADE)
    kind_code = models.CharField(max_length=10, choices=exam_kind_choices)
    mode_code = models.CharField(max_length=10, choices=exam_mode_choices)
    exam_set = models.ForeignKey(ExamSet, null=True, blank=True, related_name="attempts", on_delete=models.SET_NULL)
    section_code = models.CharField(max_length=10, blank=True)
    # Bài từ vựng: {"scope": "due"|"topics"|"mastered", "topic_ids": [...],
    # "types": [...], "srs_link": true}. Các loại khác để trống.
    scope = models.JSONField(default=dict, blank=True)
    total = models.PositiveSmallIntegerField(default=0)
    score = models.PositiveSmallIntegerField(default=0)
    current_part = models.PositiveSmallIntegerField(null=True, blank=True)
    # Mốc giờ theo phần (ISO), khoá là số phần dạng chuỗi: {"1": "...", "2": "..."}.
    # Hạn giờ KHÔNG lưu cứng — tính = bắt đầu + PART_MINUTES (apps/exam/constants.py).
    part_started_at = models.JSONField(default=dict, blank=True)
    part_submitted_at = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "-started_at"]),
            models.Index(fields=["user", "finished_at"]),
        ]
        verbose_name = "Lượt kiểm tra"
        verbose_name_plural = "Lượt kiểm tra"

    def __str__(self):
        return f"{self.user_id} - {self.kind_code} - {self.score}/{self.total}"

    @property
    def is_finished(self):
        return self.finished_at is not None


class ExamAnswer(AuditableModel):
    """Một câu trong lượt — tạo ĐỦ dòng ngay lúc bắt đầu, selected rỗng = chưa làm.

    Câu từ vựng sinh sẵn cả lượt (payload) để F5, thoát ra vào lại và màn kết
    quả luôn thấy đúng câu, đúng thứ tự phương án đã hiện.
    """

    attempt = models.ForeignKey(ExamAttempt, related_name="answers", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField(help_text="Thứ tự hiện trong lượt, từ 1")
    question = models.ForeignKey(ExamQuestion, null=True, blank=True, related_name="answers", on_delete=models.SET_NULL)
    vocabulary = models.ForeignKey(Vocabulary, null=True, blank=True, related_name="exam_answers", on_delete=models.SET_NULL)
    question_type_code = models.CharField(max_length=10, blank=True, choices=vocab_question_choices)
    # Bài từ vựng: {"prompt": ..., "options": [{"text": ..., "gloss": ...}], "correct": 1,
    #               "word": ..., "reading": ..., "meaning": ...} — correct tính từ 1.
    payload = models.JSONField(default=dict, blank=True)
    selected = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Vị trí đã chọn, từ 1")
    is_correct = models.BooleanField(default=False)
    flagged = models.BooleanField(default=False)
    answered_at = models.DateTimeField(null=True, blank=True)
    time_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["attempt", "order"]
        constraints = [
            models.UniqueConstraint(fields=["attempt", "order"], name="uniq_exam_answer_order"),
        ]
        indexes = [models.Index(fields=["attempt", "selected"])]
        verbose_name = "Câu trả lời"
        verbose_name_plural = "Câu trả lời"

    def __str__(self):
        return f"{self.attempt_id}#{self.order}"

    @property
    def is_answered(self):
        return self.selected is not None


class WrongBookManager(models.Manager):
    """Ẩn mục từ vựng của từ đã xoá mềm; mục câu đề thi (vocabulary rỗng) giữ nguyên."""

    def get_queryset(self):
        return super().get_queryset().filter(
            models.Q(vocabulary__isnull=True) | models.Q(vocabulary__is_deleted=False)
        )


class WrongBookEntry(AuditableModel):
    """Một mục trong Sổ câu sai — câu đề thi HOẶC (từ vựng, dạng câu).

    Ra khỏi sổ khi đúng 2 lần liên tiếp, hai lần khác ngày (◆4) — xem
    apps/exam/services/wrongbook.py. cleared_at rỗng = còn trong sổ.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="wrongbook", on_delete=models.CASCADE)
    question = models.ForeignKey(ExamQuestion, null=True, blank=True, related_name="wrongbook", on_delete=models.CASCADE)
    vocabulary = models.ForeignKey(Vocabulary, null=True, blank=True, related_name="wrongbook", on_delete=models.CASCADE)
    question_type_code = models.CharField(max_length=10, blank=True, choices=vocab_question_choices)
    wrong_count = models.PositiveSmallIntegerField(default=1)
    correct_streak = models.PositiveSmallIntegerField(default=0)
    last_correct_on = models.DateField(null=True, blank=True)
    last_wrong_at = models.DateTimeField()
    cleared_at = models.DateTimeField(null=True, blank=True)

    objects = WrongBookManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["last_wrong_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "question"], condition=Q(question__isnull=False),
                name="uniq_wrongbook_question",
            ),
            models.UniqueConstraint(
                fields=["user", "vocabulary", "question_type_code"], condition=Q(vocabulary__isnull=False),
                name="uniq_wrongbook_vocab",
            ),
            models.CheckConstraint(
                condition=(Q(question__isnull=False, vocabulary__isnull=True)
                           | Q(question__isnull=True, vocabulary__isnull=False)),
                name="wrongbook_one_target",
            ),
        ]
        indexes = [models.Index(fields=["user", "cleared_at"])]
        verbose_name = "Mục sổ câu sai"
        verbose_name_plural = "Sổ câu sai"

    def __str__(self):
        target = f"q{self.question_id}" if self.question_id else f"v{self.vocabulary_id}:{self.question_type_code}"
        return f"{self.user_id} - {target}"
