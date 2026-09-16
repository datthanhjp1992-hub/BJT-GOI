"""
Báo cáo lỗi nội dung (SC14) — người học bấm "🚩 Báo lỗi" ở màn từ vựng, admin
xử lý ở khu quản trị (mục "Báo cáo lỗi" trên sidebar).

VÌ SAO KHÔNG GỘP VÀO Contribution (apps/gamification):
- Góp ý là ĐỀ XUẤT nội dung (thêm từ mới / sửa nghĩa / bình luận): duyệt xong
  thì GHI vào Vocabulary và CỘNG ĐIỂM cho người gửi.
- Báo lỗi là BÁO HỎNG: không có nội dung đề xuất để ghi đè, không cộng điểm,
  và một lỗi có thể nằm ngoài từ vựng (trang vỡ, nút bấm không ăn).
Gộp chung sẽ phải cắm `if` rẽ nhánh ở mọi chỗ trong luồng duyệt + hòm thư, nên
tách bảng. Hai màn hình admin vì vậy cũng là hai màn riêng, đúng như sidebar
mockup SC07/SC12 đã vẽ sẵn ("Hòm thư góp ý" và "Báo cáo lỗi" là 2 mục).

Quy ước "không hardcode" giống mọi model khác trong dự án:
- TÊN loại lỗi / tên trạng thái nằm trong MasterCode, tra qua apps.core.mastercode.
- Field `*_code` dưới đây chỉ lưu MÃ, không lưu tên.
- Mọi chuỗi hiển thị đi qua label.properties / message.properties.
"""
from django.conf import settings
from django.db import models

from apps.core.constants import (
    CODE_TYPE_ERROR_STATUS,
    CODE_TYPE_ERROR_TYPE,
    ERROR_STATUS_DISMISSED,
    ERROR_STATUS_FIXED,
    ERROR_STATUS_PENDING,
)
from apps.core.models import AuditableModel
from apps.vocabulary.models import Vocabulary


class ErrorReport(AuditableModel):
    """Một lượt báo lỗi của người dùng."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="error_reports", on_delete=models.CASCADE
    )

    # MasterCode code_type = CODE_TYPE_ERROR_TYPE
    error_type_code = models.CharField(max_length=10)
    # MasterCode code_type = CODE_TYPE_ERROR_STATUS, mặc định "Chờ xử lý"
    status_code = models.CharField(max_length=10, default=ERROR_STATUS_PENDING)

    # Từ vựng bị báo lỗi. SET_NULL + null=True vì hai lý do:
    # (1) lỗi kỹ thuật (trang vỡ) không gắn với từ nào,
    # (2) admin sửa lỗi bằng cách XOÁ từ trùng/sai thì lịch sử báo lỗi phải còn
    #     lại để đối chiếu — cùng cách làm với Contribution.target_vocabulary.
    vocabulary = models.ForeignKey(
        Vocabulary, null=True, blank=True, related_name="error_reports",
        on_delete=models.SET_NULL,
    )

    description = models.TextField(help_text="Người dùng mô tả lỗi gặp phải.")
    suggested_fix = models.CharField(
        max_length=255, blank=True, help_text="Đề xuất sửa (tuỳ chọn)."
    )
    # Đường dẫn nơi phát hiện lỗi, lấy tự động từ HTTP_REFERER lúc gửi. Chỉ để
    # admin lần lại hiện trường, KHÔNG dùng để redirect (tránh open redirect).
    page_path = models.CharField(max_length=255, blank=True)

    # Phần admin xử lý
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="+",
        on_delete=models.SET_NULL,
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    admin_response = models.TextField(blank=True, help_text="Phản hồi hiển thị cho người báo.")

    class Meta:
        indexes = [
            models.Index(fields=["status_code"]),
            models.Index(fields=["vocabulary", "status_code"]),
        ]
        ordering = ["-created_at"]
        verbose_name = "Error report"
        verbose_name_plural = "Error reports"

    def __str__(self):
        return f"ErrorReport#{self.pk} ({self.error_type_code}) - {self.status_code}"

    # -- Tên hiển thị: luôn tra MasterCode, không tự map trong code --------
    @property
    def error_type_name(self):
        from apps.core.mastercode import get_code_name

        return get_code_name(CODE_TYPE_ERROR_TYPE, self.error_type_code)

    @property
    def status_name(self):
        from apps.core.mastercode import get_code_name

        return get_code_name(CODE_TYPE_ERROR_STATUS, self.status_code)

    @property
    def is_pending(self):
        return self.status_code == ERROR_STATUS_PENDING

    @property
    def is_fixed(self):
        return self.status_code == ERROR_STATUS_FIXED

    @property
    def is_dismissed(self):
        return self.status_code == ERROR_STATUS_DISMISSED
