"""
Nội dung KÍNH NGỮ (敬語) — app tách hẳn khỏi `vocabulary`.

VÌ SAO TÁCH (đừng gộp lại):
`Vocabulary` là bộ ba phẳng word/reading/meaning_vi — một từ, một nghĩa. Kính ngữ
là quan hệ N–1 CÓ PHÂN LOẠI: 行く có 4 dạng 尊敬語 (行かれる・いらっしゃる・
おいでになる・お越しになる), 2 dạng 謙譲語, 1 dạng 丁寧語. Nhồi 175 dòng kính ngữ
vào `Vocabulary` sẽ kéo chúng vào hàng đợi SRS của MỌI người học
(`learning.UserVocabularyProgress`) và vào phiếu luyện viết PDF (SC10).
Chi tiết: claude/keigo-thiet-ke.md.

12 model, tất cả kế thừa AuditableModel như 19 bảng còn lại của repo.
Nguồn dữ liệu: Thaolejp – Khóa BJT Kính ngữ (04/2025).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.constants import (
    QUESTION_TYPE_ORDERING,
    keigo_pair_type_choices,
    keigo_style_choices,
    question_type_choices,
)
from apps.core.models import AuditableModel

SOURCE_NOTE = "Thaolejp - Khoa BJT Kinh ngu (04/2025)"


# ===========================================================================
# NHÓM A — Nội dung kính ngữ
# ===========================================================================


class KeigoLesson(AuditableModel):
    """Một chương trên web (7 chương, bám đúng mục lục sách)."""

    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=80, unique=True)
    style_code = models.CharField(
        max_length=20, blank=True, choices=keigo_style_choices,
        help_text="MasterCode '14'. Để trống với chương nội dung hỗn hợp.",
    )
    summary_vi = models.TextField(blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    source_note = models.CharField(max_length=255, blank=True, default=SOURCE_NOTE)

    class Meta:
        ordering = ["display_order", "slug"]
        verbose_name = "Chương kính ngữ"
        verbose_name_plural = "Chương kính ngữ"

    def __str__(self):
        return self.title


class KeigoVerb(AuditableModel):
    """Động từ gốc 基本形 — cột đầu của bảng chia động từ trang 13-16.

    LƯU Ý: `reading` để TRỐNG toàn bộ trong dữ liệu thật vì sách không in cách
    đọc cho cột 基本形. Khoá tự nhiên vẫn là CẶP (plain_form, reading) theo đúng
    bài học đã rút ra ở `Vocabulary` — 同形異音語 cùng mặt chữ khác cách đọc là
    hai từ khác hẳn nhau. Với reading rỗng, khoá thoái hoá về mình plain_form;
    chừng nào còn nhập reading rỗng thì `update_or_create` vẫn idempotent, nhưng
    điền reading cho MỘT nửa số dòng sẽ tạo bản ghi trùng thay vì cập nhật.
    """

    plain_form = models.CharField(max_length=50, help_text="vd 言う, 風邪を引く")
    reading = models.CharField(max_length=80, blank=True)
    meaning_vi = models.CharField(max_length=150, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "plain_form"]
        constraints = [
            models.UniqueConstraint(
                fields=["plain_form", "reading"], name="uniq_keigo_verb_form_reading"
            ),
        ]
        verbose_name = "Động từ gốc"
        verbose_name_plural = "Động từ gốc"

    def __str__(self):
        return f"{self.plain_form} ({self.reading})" if self.reading else self.plain_form


class KeigoForm(AuditableModel):
    """Một dạng kính ngữ của một động từ — BẢNG LÕI của app.

    Một hàng trong bảng 4 cột của sách = 1 KeigoVerb + N KeigoForm. Ô ghi "—"
    (vd 風邪を引く không có 謙譲語) thì KHÔNG tạo row, không tạo row rỗng.

    Hai bảng "các trường hợp đặc biệt" trang 4 và 7 KHÔNG cần bảng riêng —
    chúng chỉ là filter(is_irregular=True, style_code=...).

    style_code cho 謙譲語 — sách chỉ phân I/II ở đúng hai bảng nhỏ trang 7:
      - có trong bảng Khiêm nhường ngữ I trang 7   -> kenjo1
      - có trong bảng Khiêm nhường ngữ II trang 7  -> kenjo2
      - mọi dòng còn lại (cột 謙譲語 bảng tr.13-16, bảng 拝 tr.9) -> kenjo
    Đừng suy đoán I/II cho những dòng sách không nói — đã từng làm và phải sửa
    lại toàn bộ 48 dòng.
    """

    verb = models.ForeignKey(KeigoVerb, related_name="forms", on_delete=models.CASCADE)
    style_code = models.CharField(max_length=20, choices=keigo_style_choices)
    form = models.CharField(max_length=80, help_text="vd おっしゃる, お読みになる")
    reading = models.CharField(max_length=120, blank=True)
    is_irregular = models.BooleanField(
        default=False, help_text="True = thuộc bảng 'các trường hợp đặc biệt' (tr.4 / tr.7 / tr.9).",
    )
    note_vi = models.CharField(
        max_length=255, blank=True,
        help_text="Ghi chú in màu đỏ trong ô của sách, vd （自分が一方的に行う行為の場合）.",
    )
    # Cây cầu sang từ điển: nếu おっしゃる đã có trong Vocabulary thì nối lại để
    # trang từ vựng hiện được "đây là 尊敬語 của 言う". Nullable vì phần lớn dạng
    # kính ngữ KHÔNG có trong từ điển, và thiếu từ vựng không được chặn nhập.
    vocabulary = models.ForeignKey(
        "vocabulary.Vocabulary", null=True, blank=True,
        related_name="keigo_forms", on_delete=models.SET_NULL,
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["verb_id", "display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["verb", "style_code", "form"], name="uniq_keigo_form"
            ),
        ]
        indexes = [models.Index(fields=["style_code", "is_irregular"])]
        verbose_name = "Dạng kính ngữ"
        verbose_name_plural = "Dạng kính ngữ"

    def __str__(self):
        return f"{self.verb_id}:{self.style_code}:{self.form}"


class KeigoPattern(AuditableModel):
    """Mẫu ngữ pháp (お・ご〜になる, 〜ていらっしゃる, ...).

    `code` tồn tại vì khoá tự nhiên lẽ ra là cặp (lesson, title), mà `title`
    chứa toàn 「」／〜 nên chép sang file con cực dễ sai một ký tự. Một cột slug
    phẳng làm FK của KeigoExample chỉ còn MỘT cột: `pattern__code`.
    """

    code = models.SlugField(max_length=60, unique=True, help_text="vd sonkei-o-go-ni-naru")
    lesson = models.ForeignKey(KeigoLesson, related_name="patterns", on_delete=models.CASCADE)
    style_code = models.CharField(max_length=20, blank=True, choices=keigo_style_choices)
    title = models.CharField(max_length=120, help_text="Chép nguyên tiêu đề mẫu trong sách.")
    formation = models.CharField(max_length=255, blank=True, help_text="vd お/ご + Vます形 + になる")
    explanation_vi = models.TextField(
        blank=True, help_text="Sách gốc KHÔNG có giải thích tiếng Việt — tự viết thêm.",
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["lesson_id", "display_order"]
        verbose_name = "Mẫu ngữ pháp kính ngữ"
        verbose_name_plural = "Mẫu ngữ pháp kính ngữ"

    def __str__(self):
        return self.title


class KeigoExample(AuditableModel):
    """Câu ví dụ của một mẫu ngữ pháp.

    Ba trường speaker / is_correct / pair_group cho phép MỘT bảng chứa cả ba
    kiểu ví dụ trong sách:
      - ví dụ thường         -> is_correct=True, pair_group=null
      - cặp sai–đúng (×/○)   -> 2 row cùng pair_group, khác is_correct
      - hội thoại A「」B「」 -> 2 row cùng pair_group, khác speaker

    Câu nối bằng ／ hoặc ＝ (hai cách nói tương đương) thì TÁCH 2 row và KHÔNG
    gán pair_group — quy ước đã áp dụng nhất quán cho toàn bộ dữ liệu.

    Bảng cặp từ biến đổi (安い→安うございます, です→でございます) KHÔNG thuộc về
    đây mà là KeigoPhrasePair — chúng là cặp từ, không phải câu.
    """

    pattern = models.ForeignKey(KeigoPattern, related_name="examples", on_delete=models.CASCADE)
    sentence_jp = models.CharField(max_length=400, help_text="Có cú pháp ruby {漢字|かんじ}.")
    sentence_vi = models.CharField(max_length=400, blank=True)
    speaker = models.CharField(max_length=30, blank=True, help_text="A / B / 客 / 係員 ...")
    is_correct = models.BooleanField(default=True, help_text="False = câu bị đánh dấu ×.")
    pair_group = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Gom các dòng cùng một hội thoại / cùng một cặp ×–○. Đánh số riêng trong mỗi mẫu.",
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["pattern_id", "display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["pattern", "sentence_jp"], name="uniq_keigo_example"
            ),
        ]
        verbose_name = "Câu ví dụ kính ngữ"
        verbose_name_plural = "Câu ví dụ kính ngữ"

    def __str__(self):
        return self.sentence_jp[:60]


class KeigoPhrasePair(AuditableModel):
    """Các bảng cặp từ & từ đệm của trang 11 và 17-21.

    8 bảng trông khác nhau nhưng cùng một hình dạng (một vế thường, một vế lịch
    sự, đôi khi có nhãn nhóm) -> gom vào một bảng + `pair_type` (MasterCode 15),
    không làm 8 model gần giống nhau.

    `casual` để TRỐNG với `cushion` (cụm từ đệm không có vế đối) và với hai dòng
    quy tắc chung của `teinei_rule` (後ろに「です」「ます」を付ける / 前に「お」
    「ご」などを付ける) — cả câu đặt vào `polite`.
    """

    lesson = models.ForeignKey(KeigoLesson, related_name="phrase_pairs", on_delete=models.CASCADE)
    pair_type = models.CharField(max_length=20, choices=keigo_pair_type_choices)
    group_label = models.CharField(max_length=120, blank=True)
    casual = models.CharField(max_length=200, blank=True, help_text="Vế trái / vế SAI.")
    polite = models.CharField(max_length=200, help_text="Vế phải / vế ĐÚNG / cụm từ đệm.")
    note_vi = models.CharField(max_length=255, blank=True)
    # Đánh số riêng trong phạm vi từng pair_type (KHÔNG theo lesson) vì UI nhóm
    # theo pair_type — một bảng trong sách = một pair_type.
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["pair_type", "display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["pair_type", "casual", "polite"], name="uniq_keigo_phrase_pair"
            ),
        ]
        verbose_name = "Cặp từ kính ngữ"
        verbose_name_plural = "Cặp từ kính ngữ"

    def __str__(self):
        return f"{self.casual} → {self.polite}" if self.casual else self.polite


# ===========================================================================
# NHÓM B — Bài tập (262 câu)
# ===========================================================================


class ExerciseSet(AuditableModel):
    """Một bộ đề — 17 bộ: LUYỆN TẬP + BÀI TẬP 1..16."""

    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=40, unique=True)
    lesson = models.ForeignKey(
        KeigoLesson, null=True, blank=True, related_name="exercise_sets", on_delete=models.SET_NULL,
    )
    display_order = models.PositiveSmallIntegerField(default=0)
    question_count = models.PositiveSmallIntegerField(
        default=0, help_text="ĐẾM THEO BẢNG ĐÁP ÁN trang 52-54, không theo mục lục (mục lục sai).",
    )
    source_note = models.CharField(max_length=255, blank=True, default=SOURCE_NOTE)

    class Meta:
        ordering = ["display_order", "slug"]
        verbose_name = "Bộ đề kính ngữ"
        verbose_name_plural = "Bộ đề kính ngữ"

    def __str__(self):
        return self.title


class ExerciseSection(AuditableModel):
    """MỘT ĐOẠN VĂN DÙNG CHUNG — không phải một 問題.

    Trong sách, một 問題 có thể chứa nhiều đoạn văn tách biệt:
      - BÀI TẬP 12 問題2 (tr.39-40): hai khung riêng, khung 1 chứa (11)(12),
        khung 2 (lá thư) chứa (13)(14)(15).
      - LUYỆN TẬP 問題3 (tr.24): ba đoạn hội thoại (1)(2)(3).
    Vì mỗi section chỉ có MỘT `passage_jp`, một 問題 có N đoạn phải tách thành N
    section (`number` đánh tiếp, `instruction_jp` chép giống nhau). Gộp lại =
    mất đoạn văn thứ hai trở đi.
    """

    exercise_set = models.ForeignKey(ExerciseSet, related_name="sections", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField(help_text="Số của 問題; đoạn thứ 2 trở đi đánh tiếp.")
    instruction_jp = models.TextField(blank=True)
    passage_jp = models.TextField(
        blank=True, help_text="Chỉ điền khi có đoạn văn dùng chung cho nhiều câu.",
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["exercise_set_id", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["exercise_set", "number"], name="uniq_keigo_section"
            ),
        ]
        verbose_name = "Phần đề (問題)"
        verbose_name_plural = "Phần đề (問題)"

    def __str__(self):
        return f"{self.exercise_set_id} - 問題{self.number}"


class Question(AuditableModel):
    """Một câu hỏi.

    `question_type` nằm ở CẤP CÂU, không phải cấp bộ đề hay cấp 問題 — BÀI TẬP 6
    và BÀI TẬP 8 có tiêu đề 問題 nói là chọn điền vào （ ） nhưng vài câu cuối
    lại là dạng ★ sắp xếp. Đây là lỗi thiết kế dễ mắc nhất ở màn này.

    `code` phẳng (bt03-q07) làm FK của QuestionOption — xem ghi chú ở KeigoPattern.
    """

    code = models.SlugField(max_length=30, unique=True, help_text="vd bt03-q07, lt-m2-q05")
    section = models.ForeignKey(ExerciseSection, related_name="questions", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField(help_text="Số câu in trong sách.")
    question_type = models.CharField(max_length=20, choices=question_type_choices)
    context_note = models.CharField(max_length=120, blank=True, help_text="（レストランで）...")
    stem_jp = models.TextField(help_text="Chỗ trống ký hiệu ____ , ô sao __★__ .")
    star_position = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Vị trí ô ★ (1-4). CHỈ dạng ordering.",
    )
    correct_order = models.CharField(
        max_length=8, blank=True, help_text="4 chữ số, vd 4321. CHỈ dạng ordering.",
    )
    explanation_vi = models.TextField(blank=True, help_text="Sách không có lời giải — viết dần.")
    difficulty = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["section_id", "number"]
        verbose_name = "Câu hỏi"
        verbose_name_plural = "Câu hỏi"

    def __str__(self):
        return self.code

    @property
    def is_ordering(self):
        return self.question_type == QUESTION_TYPE_ORDERING

    def expected_correct_position(self):
        """Phương án ĐÚNG suy ra từ (star_position, correct_order), hoặc None.

        Đáp án sách ghi `3(1234)` = vế số 3 vào ô ★, thứ tự đầy đủ 1-2-3-4. Hai
        thông tin đó thừa nhau, và chính sự thừa ấy là cơ chế bắt lỗi nhập liệu.
        """
        order = (self.correct_order or "").strip()
        if not self.is_ordering or sorted(order) != list("1234"):
            return None
        if not self.star_position or not (1 <= self.star_position <= 4):
            return None
        return int(order[self.star_position - 1])

    def clean(self):
        errors = {}
        order = (self.correct_order or "").strip()
        if self.is_ordering:
            if sorted(order) != list("1234"):
                errors["correct_order"] = (
                    "Dạng sắp xếp: correct_order phải gồm đúng 4 chữ số 1,2,3,4 "
                    "mỗi chữ một lần (vd 4321)."
                )
            if self.star_position is None or not (1 <= self.star_position <= 4):
                errors["star_position"] = "Dạng sắp xếp: star_position phải từ 1 đến 4."
            # Kiểm chéo với phương án — chỉ chạy được khi câu đã có phương án
            # trong DB. Lúc nhập file 09 thì file 10 chưa nạp, nên phép kiểm
            # THẬT SỰ nằm ở QuestionOption.clean() và lệnh check_keigo_data.
            if not errors and self.pk:
                marked = [o.position for o in self.options.filter(is_correct=True)]
                expect = self.expected_correct_position()
                if len(marked) == 1 and expect is not None and marked[0] != expect:
                    errors["correct_order"] = (
                        f"Lệch đáp án: ô ★ ở vị trí {self.star_position}, "
                        f"correct_order='{order}' => phải là phương án {expect}, "
                        f"nhưng phương án đang đánh đúng là {marked[0]}."
                    )
        else:
            if order:
                errors["correct_order"] = "Chỉ dạng 'ordering' mới có correct_order."
            if self.star_position is not None:
                errors["star_position"] = "Chỉ dạng 'ordering' mới có star_position."
        if errors:
            raise ValidationError(errors)


class QuestionOption(AuditableModel):
    """Một phương án. Số phương án do dữ liệu quyết định, KHÔNG cố định 4 —
    LUYỆN TẬP in sẵn 2-3 phương án trong ngoặc （もらった／くれた）."""

    question = models.ForeignKey(Question, related_name="options", on_delete=models.CASCADE)
    position = models.PositiveSmallIntegerField(help_text="Số thứ tự in trong sách (1-4).")
    text_jp = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["question_id", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "position"], name="uniq_keigo_option_position"
            ),
        ]
        verbose_name = "Phương án"
        verbose_name_plural = "Phương án"

    def __str__(self):
        return f"{self.question_id}.{self.position}"

    def clean(self):
        """Phép kiểm chéo THẬT SỰ chạy ở đây — lúc nhập file 10 thì câu hỏi đã
        có sẵn trong DB, nên cả `correct_order` lẫn phương án đúng đều có mặt."""
        if not self.is_correct or not self.question_id:
            return
        expect = self.question.expected_correct_position()
        if expect is not None and self.position != expect:
            raise ValidationError({
                "position": (
                    f"Lệch đáp án: câu {self.question.code} có ô ★ ở vị trí "
                    f"{self.question.star_position} và correct_order="
                    f"'{self.question.correct_order}' => phương án đúng phải là "
                    f"{expect}, không phải {self.position}."
                )
            })


class UserExerciseAttempt(AuditableModel):
    """Một lượt làm bài của một người học."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="keigo_attempts", on_delete=models.CASCADE,
    )
    exercise_set = models.ForeignKey(ExerciseSet, related_name="attempts", on_delete=models.CASCADE)
    score = models.PositiveSmallIntegerField(default=0)
    total = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["user", "-started_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "exercise_set", "started_at"], name="uniq_keigo_attempt"
            ),
        ]
        verbose_name = "Lượt làm bài kính ngữ"
        verbose_name_plural = "Lượt làm bài kính ngữ"

    def __str__(self):
        return f"{self.user_id} - {self.exercise_set_id} - {self.score}/{self.total}"


class UserQuestionAnswer(AuditableModel):
    """Câu trả lời cho TỪNG câu.

    Lưu từng câu (không chỉ điểm tổng) để làm được màn 'xem lại câu sai' và sau
    này thống kê 'mẫu ngữ pháp nào bạn hay sai' — thứ mà chỉ lưu điểm tổng thì
    vĩnh viễn không làm được.
    """

    attempt = models.ForeignKey(
        UserExerciseAttempt, related_name="answers", on_delete=models.CASCADE,
    )
    question = models.ForeignKey(Question, related_name="answers", on_delete=models.CASCADE)
    selected_option = models.ForeignKey(
        QuestionOption, null=True, blank=True, related_name="+", on_delete=models.SET_NULL,
    )
    selected_order = models.CharField(max_length=8, blank=True, help_text="Dạng ordering.")
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["attempt_id", "question_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"], name="uniq_keigo_answer"
            ),
        ]
        verbose_name = "Câu trả lời kính ngữ"
        verbose_name_plural = "Câu trả lời kính ngữ"

    def __str__(self):
        return f"{self.attempt_id} - {self.question_id}"
