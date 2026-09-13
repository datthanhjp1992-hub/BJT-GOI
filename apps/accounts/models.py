"""
Custom User model extended with app-specific profile fields:
- ui_theme: which of the 3 mockup styles (A/B/C) the user picked in Settings
- total_points: tổng điểm đóng góp cộng đồng (denormalize từ
  apps.gamification.UserPointTransaction để không phải SUM() mỗi request —
  cập nhật trong apps.gamification.services.award_points() bằng F())
- streak/số từ đã thuộc lấy động từ app learning, không lưu ở đây

`ui_theme` KHÔNG hardcode choices=[...] — lấy động từ
MasterCode qua apps.core.constants (xem file đó + docs/SPEC_GOP_Y_THANH_TICH.md
mục 2). Django cho phép `choices=<callable>` nên vẫn khai báo bình thường ở
field, chỉ khác là truyền hàm thay vì list cứng.

AUDIT: User cũng kế thừa AuditableModel để đủ 4 cột created_at/created_by/
updated_at/updated_by trên MỌI bảng của dự án. created_by/updated_by ở đây là
khoá ngoại tự trỏ về chính accounts_user (null khi user tự đăng ký hoặc khi
tạo bằng createsuperuser — lúc đó không có request nào để lấy actor).
AuditableModel đứng TRƯỚC AbstractUser trong danh sách kế thừa để save() của
nó nằm trong MRO; Meta lấy lại từ AbstractUser để giữ verbose_name gốc.
"""
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone as dj_timezone

from apps.core.constants import ui_theme_choices
from apps.core.models import AuditableModel


class User(AuditableModel, AbstractUser):
    ui_theme = models.CharField(
        max_length=1, choices=ui_theme_choices, default="A",
        help_text="Selected UI style, set from the Settings screen (SC08_CaiDat).",
    )
    daily_review_goal = models.PositiveSmallIntegerField(default=20)

    # Múi giờ IANA của NGƯỜI HỌC, không phải của server. Quyết định mốc đổi
    # ngày khi tính bài đến hạn (UserVocabularyProgress.next_review_date) và
    # streak. Không dùng MasterCode vì đây là danh sách chuẩn IANA, không phải
    # dữ liệu nghiệp vụ do admin tự định nghĩa.
    timezone = models.CharField(
        max_length=64, default=settings.TIME_ZONE,
        help_text="Múi giờ IANA, vd 'Asia/Tokyo' hoặc 'Asia/Ho_Chi_Minh'.",
    )
    daily_reminder_enabled = models.BooleanField(default=True)
    weekly_email_summary_enabled = models.BooleanField(default=False)

    total_points = models.PositiveIntegerField(
        default=0,
        help_text="Tổng điểm đóng góp cộng đồng — cache, không sửa tay, xem apps.gamification.services.",
    )

    class Meta(AbstractUser.Meta):
        pass

    @property
    def tzinfo(self):
        """ZoneInfo của user; rơi về TIME_ZONE của server nếu giá trị không hợp lệ."""
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo(settings.TIME_ZONE)

    def local_now(self):
        """'Bây giờ' theo múi giờ của user."""
        return dj_timezone.localtime(dj_timezone.now(), self.tzinfo)

    def local_today(self):
        """'Hôm nay' theo múi giờ của user — dùng cho lịch ôn và streak."""
        return self.local_now().date()

    def __str__(self):
        return self.username
