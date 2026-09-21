"""
Góp ý (Contribution) + Điểm (Point) + Danh hiệu nhiều nhóm (Badge).
Xem docs/SPEC_GOP_Y_THANH_TICH.md để biết luồng nghiệp vụ đầy đủ.

Quy ước "không hardcode":
- TÊN hiển thị (loại góp ý, trạng thái, tên từng bậc danh hiệu...) luôn nằm
  trong MasterCode (apps.core.models.MasterCode), tra qua apps.core.mastercode.
- code_type nào dùng ở đâu -> xem apps.core.constants.
- Field `code_type` / `*_code` dưới đây chỉ lưu MÃ (vd "001"), không lưu tên.
- Cái KHÔNG chuyển vào MasterCode được: `BadgeCategory.metric` — đây là lựa
  chọn kỹ thuật quyết định CHẠY HÀM TÍNH NÀO (apps.gamification.services),
  không phải dữ liệu hiển thị, nên vẫn là 1 choices Python cố định. Thêm 1
  metric mới luôn cần thêm code tính toán tương ứng, không thể chỉ thêm data.
"""
from django.conf import settings
from django.db import models

from apps.core.models import AuditableModel
from apps.core.constants import (
    CODE_TYPE_CONTRIBUTION_TYPE,
    CODE_TYPE_CONTRIBUTION_STATUS,
    CODE_TYPE_POINT_ACTION,
)
from apps.vocabulary.models import Vocabulary, Topic


# --------------------------------------------------------------------------
# Góp ý
# --------------------------------------------------------------------------

class Contribution(AuditableModel):
    """1 góp ý — từ mới / sửa nghĩa / bình luận — gộp chung 1 bảng vì cả 3
    dùng chung 1 hòm thư + 1 luồng duyệt (xem spec mục 3)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="contributions", on_delete=models.CASCADE)

    # MasterCode code_type = CODE_TYPE_CONTRIBUTION_TYPE ("Từ mới"/"Sửa nghĩa"/"Bình luận")
    contribution_type_code = models.CharField(max_length=10)
    # MasterCode code_type = CODE_TYPE_CONTRIBUTION_STATUS, default "001" = Chờ duyệt
    status_code = models.CharField(max_length=10, default="001")

    # "Sửa nghĩa" & "Bình luận": từ đang được góp ý. Để trống với "Từ mới".
    #
    # SET_NULL chứ KHÔNG phải CASCADE: bình luận đã duyệt là nội dung công khai
    # và điểm đã trao cho nó là lịch sử — xoá một từ vựng (gộp bản trùng, sửa
    # chính tả rồi tạo lại) không được phép xoá theo cả hai thứ đó. Cách này
    # cũng thống nhất với UserPointTransaction.contribution vốn đã SET_NULL.
    #
    # Hệ quả: target_vocabulary = None mang HAI nghĩa — góp ý loại "Từ mới"
    # (chưa từng có target) và góp ý mồ côi vì từ bị xoá. Phân biệt bằng
    # contribution_type_code.
    target_vocabulary = models.ForeignKey(
        Vocabulary, null=True, blank=True, related_name="contributions",
        on_delete=models.SET_NULL,
    )

    # "Từ mới" / "Sửa nghĩa": nội dung đề xuất.
    proposed_word = models.CharField(max_length=100, blank=True)
    proposed_reading = models.CharField(max_length=150, blank=True)
    proposed_meaning_vi = models.CharField(max_length=255, blank=True)
    proposed_topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.SET_NULL)

    # "Bình luận": nội dung hiển thị công khai dưới từ vựng SAU KHI duyệt.
    comment_text = models.TextField(blank=True)

    # Xử lý của admin
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="+", on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_response = models.TextField(blank=True)
    points_awarded = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["status_code"]),
            models.Index(fields=["contribution_type_code", "target_vocabulary"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Contribution#{self.pk} ({self.contribution_type_code}) - {self.status_code}"

    @property
    def type_name(self):
        from apps.core.mastercode import get_code_name
        return get_code_name(CODE_TYPE_CONTRIBUTION_TYPE, self.contribution_type_code)

    @property
    def status_name(self):
        from apps.core.mastercode import get_code_name
        return get_code_name(CODE_TYPE_CONTRIBUTION_STATUS, self.status_code)


# --------------------------------------------------------------------------
# Điểm
# --------------------------------------------------------------------------

class PointRule(AuditableModel):
    """Số điểm cho mỗi action_code (MasterCode code_type = CODE_TYPE_POINT_ACTION).
    Sửa số điểm = sửa data ở đây, KHÔNG sửa code."""

    action_code = models.CharField(max_length=10, unique=True)
    points = models.IntegerField()

    class Meta:
        ordering = ["action_code"]

    def __str__(self):
        from apps.core.mastercode import get_code_name
        name = get_code_name(CODE_TYPE_POINT_ACTION, self.action_code, default=self.action_code)
        return f"{name}: {self.points:+d}"


class UserPointTransaction(AuditableModel):
    """Log mỗi lần cộng/trừ điểm — dùng để audit và hiển thị lịch sử điểm (SC13)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="point_transactions", on_delete=models.CASCADE)
    action_code = models.CharField(max_length=10)  # MasterCode code_type = CODE_TYPE_POINT_ACTION
    points = models.IntegerField()
    contribution = models.ForeignKey(Contribution, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} {self.points:+d} ({self.action_code})"

    @property
    def action_name(self):
        """Tên hành động để hiện ở bảng "Lịch sử điểm" (SC13) — tra MasterCode
        như Contribution.type_name, không lưu tên trong bảng log."""
        from apps.core.mastercode import get_code_name
        return get_code_name(CODE_TYPE_POINT_ACTION, self.action_code, default=self.action_code)


# --------------------------------------------------------------------------
# Danh hiệu — nhiều nhóm, mỗi nhóm 1 code_type riêng trong MasterCode
# --------------------------------------------------------------------------

class BadgeCategory(AuditableModel):
    """
    1 NHÓM danh hiệu — vd 'Đóng góp cộng đồng', 'Học tập', 'Kiểm tra'. Mỗi
    category ứng với 1 code_type riêng trong MasterCode (đúng yêu cầu: "badge
    riêng nằm ở codeType riêng"), TÊN từng bậc (BadgeTier) tra qua đó.

    Thêm 1 nhóm danh hiệu mới = (1) thêm code_type mới trong
    apps.core.constants, (2) seed tên các bậc vào MasterCode
    (seed_mastercode.py), (3) tạo 1 row BadgeCategory ở đây trỏ tới code_type
    đó + chọn metric, (4) tạo các BadgeTier ứng với ngưỡng số. KHÔNG cần sửa
    model nào khác.
    """

    METRIC_CONTRIBUTION_POINTS = "CONTRIBUTION_POINTS"
    METRIC_WORDS_LEARNED = "WORDS_LEARNED"
    METRIC_QUIZ_HIGH_SCORE_COUNT = "QUIZ_HIGH_SCORE_COUNT"
    METRIC_CHOICES = [
        (METRIC_CONTRIBUTION_POINTS, "Tổng điểm đóng góp"),
        (METRIC_WORDS_LEARNED, "Số từ đã học thuộc"),
        (METRIC_QUIZ_HIGH_SCORE_COUNT, "Số bài kiểm tra đạt điểm cao"),
    ]

    code_type = models.CharField(
        max_length=10, unique=True,
        help_text="code_type tương ứng bên MasterCode, vd '07' cho nhóm 'Học tập'.",
    )
    name = models.CharField(max_length=150, help_text="Tên nhóm danh hiệu, vd 'Học tập'.")
    metric = models.CharField(
        max_length=40, choices=METRIC_CHOICES,
        help_text="Đại lượng dùng để xét bậc — quyết định hàm tính trong apps.gamification.services.",
    )
    icon_emoji = models.CharField(max_length=8, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order"]
        verbose_name_plural = "Badge categories"

    def __str__(self):
        return self.name

    def tier_name(self, code):
        from apps.core.mastercode import get_code_name
        return get_code_name(self.code_type, code)


class BadgeTier(AuditableModel):
    """1 bậc trong 1 BadgeCategory — code khớp với MasterCode ở
    code_type = category.code_type, min_value là ngưỡng đạt được."""

    category = models.ForeignKey(BadgeCategory, related_name="tiers", on_delete=models.CASCADE)
    code = models.CharField(max_length=10)
    min_value = models.PositiveIntegerField(help_text="Ngưỡng đạt bậc này, đơn vị tuỳ theo category.metric.")
    icon_emoji = models.CharField(max_length=8, blank=True)

    class Meta:
        unique_together = ("category", "code")
        ordering = ["category", "min_value"]

    def __str__(self):
        return f"{self.category.name} · {self.category.tier_name(self.code)} (>= {self.min_value})"


class UserPinnedBadge(AuditableModel):
    """
    Cơ chế "tuỳ chỉnh danh hiệu": user chọn 1 vài BadgeCategory để GHIM hiển
    thị nổi bật trên hồ sơ/navbar, thay vì hệ thống tự chọn. Chỉ được ghim
    category mà user ĐÃ đạt ít nhất 1 bậc — validate ở
    apps.gamification.services.pin_badge, không phải ở model.

    Giới hạn số lượng ghim tối đa: apps.gamification.services.MAX_PINNED_BADGES.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="pinned_badges", on_delete=models.CASCADE)
    category = models.ForeignKey(BadgeCategory, on_delete=models.CASCADE)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("user", "category")
        ordering = ["display_order"]

    def __str__(self):
        return f"{self.user} pinned {self.category}"
