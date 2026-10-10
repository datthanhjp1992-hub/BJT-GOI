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

from apps.core.constants import COLOR_SCHEME_AUTO, color_scheme_choices, ui_theme_choices
from apps.core.models import AuditableModel


class User(AuditableModel, AbstractUser):
    ui_theme = models.CharField(
        max_length=1, choices=ui_theme_choices, default="A",
        help_text="Selected UI style, set from the Settings screen (SC08_CaiDat).",
    )
    # Sáng / tối / theo thiết bị (spec.md T2.3) — base.html đặt thành
    # <html data-scheme="...">, CSS theme đổi bảng màu theo đó.
    color_scheme = models.CharField(
        max_length=10, choices=color_scheme_choices, default=COLOR_SCHEME_AUTO,
        help_text="MasterCode code_type 18: auto / light / dark.",
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
    # Hiện khoảng cách ôn lại ("1 phút", "4 ngày") dưới 4 nút chấm của SC04.
    # Mặc định ẩn: từ 01/10/2026 từ đang học chỉ quay lại khi hết lượt nên
    # con số phút không còn khớp trải nghiệm; ai quen Anki thì bật ở SC08.
    show_review_interval = models.BooleanField(default=False)
    # SC04 hiện thẻ 2 bước (02/10/2026, spec.md T1.4): mặt trước chỉ có mặt
    # chữ, lật mới thấy nghĩa. Mặc định HIỆN cách đọc ở mặt trước vì người mới
    # chưa đọc được kanji; người đã quen tắt ở SC08 để tự luyện cả cách đọc.
    show_reading_on_front = models.BooleanField(default=True)
    # Bảng hướng dẫn vuốt thẻ trên điện thoại (spec.md T6.6). Người học tích
    # "Không hiện lại" ngay trên bảng -> False; bật lại được ở SC08. Lưu ở DB
    # (không chỉ localStorage) vì trình duyệt chặn lưu trữ thì bảng hiện mãi.
    show_swipe_coach = models.BooleanField(default=True)

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
