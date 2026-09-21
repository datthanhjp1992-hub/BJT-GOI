"""
Seed PointRule + BadgeCategory + BadgeTier (ngưỡng số, không phải tên hiển
thị — tên hiển thị nằm trong MasterCode, seed bằng `seed_mastercode`).
Chạy sau seed_mastercode: python manage.py seed_mastercode && python manage.py seed_gamification

Idempotent — chạy lại để cập nhật số điểm/ngưỡng nếu bạn sửa trong
POINT_RULE_SEED / BADGE_CATEGORY_SEED bên dưới.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.constants import (
    CODE_TYPE_POINT_ACTION,
    CODE_TYPE_BADGE_CONTRIBUTION,
    CODE_TYPE_BADGE_LEARNING,
    CODE_TYPE_BADGE_QUIZ,
)

# action_code -> points — khớp mô tả trong seed_mastercode.SEED_DATA[CODE_TYPE_POINT_ACTION]
POINT_RULE_SEED = {
    "001": 1,   # Gửi góp ý từ mới
    "002": 10,  # Từ mới được duyệt
    "003": 1,   # Gửi sửa nghĩa/cách dùng
    "004": 5,   # Sửa nghĩa được duyệt
    "005": 2,   # Bình luận được duyệt
}

# code_type -> (tên category, metric, icon nhóm, [(code, min_value, icon bậc), ...])
#
# Mỗi BẬC có icon riêng (mockup SC13: 🌱 → 🌿 → 🌟 → 🏆 → 👑, nhìn là biết mình
# đang ở đâu). Bỏ trống thì SC13 lấy icon của cả nhóm cho mọi bậc, 5 ô giống
# hệt nhau.
BADGE_CATEGORY_SEED = {
    CODE_TYPE_BADGE_CONTRIBUTION: (
        "Đóng góp cộng đồng", "CONTRIBUTION_POINTS", "🌟",
        [("001", 0, "🌱"), ("002", 50, "🌿"), ("003", 200, "🌟"),
         ("004", 500, "🏆"), ("005", 1000, "👑")],
    ),
    CODE_TYPE_BADGE_LEARNING: (
        "Học tập", "WORDS_LEARNED", "📚",
        [("001", 50, "📗"), ("002", 200, "📘"), ("003", 500, "📙"),
         ("004", 1000, "📚"), ("005", 2000, "🎓")],
    ),
    CODE_TYPE_BADGE_QUIZ: (
        "Kiểm tra", "QUIZ_HIGH_SCORE_COUNT", "🎯",
        [("001", 1, "🎲"), ("002", 10, "🎯"), ("003", 30, "🏹"), ("004", 50, "🥇")],
    ),
}


class Command(BaseCommand):
    help = "Seed PointRule + BadgeCategory + BadgeTier (idempotent). Chạy sau seed_mastercode."

    def handle(self, *args, **options):
        from apps.gamification.models import PointRule, BadgeCategory, BadgeTier

        with transaction.atomic():
            for action_code, points in POINT_RULE_SEED.items():
                PointRule.objects.update_or_create(
                    action_code=action_code, defaults={"points": points}
                )

            for i, (code_type, (name, metric, icon, tiers)) in enumerate(BADGE_CATEGORY_SEED.items()):
                category, _ = BadgeCategory.objects.update_or_create(
                    code_type=code_type,
                    defaults={"name": name, "metric": metric, "icon_emoji": icon, "sort_order": i},
                )
                for code, min_value, tier_icon in tiers:
                    BadgeTier.objects.update_or_create(
                        category=category, code=code,
                        defaults={"min_value": min_value, "icon_emoji": tier_icon},
                    )

        self.stdout.write(self.style.SUCCESS(
            f"Đã seed {len(POINT_RULE_SEED)} PointRule và {len(BADGE_CATEGORY_SEED)} BadgeCategory."
        ))
