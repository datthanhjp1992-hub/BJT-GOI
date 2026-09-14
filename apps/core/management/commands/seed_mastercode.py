"""
Nạp dữ liệu MasterCode ban đầu — chạy: python manage.py seed_mastercode

Idempotent (dùng update_or_create): chạy lại nhiều lần không tạo trùng, và
sẽ CẬP NHẬT code_name/mother_code/description/sort_order nếu bạn sửa trong
SEED_DATA rồi chạy lại — nhưng KHÔNG đụng tới is_active nếu admin đã tắt tay
1 code nào đó qua trang quản trị (xem cờ PROTECTED_FIELDS bên dưới).

Đây là nơi DUY NHẤT liệt kê "code cứng" trong toàn hệ thống — vì seed data
luôn phải có 1 nguồn khởi tạo nào đó. Từ sau khi seed xong, mọi model khác
tra cứu qua apps.core.mastercode, không định nghĩa choices cứng nữa.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.constants import (
    CODE_TYPE_UI_THEME,
    CODE_TYPE_CONTRIBUTION_TYPE,
    CODE_TYPE_CONTRIBUTION_STATUS,
    CODE_TYPE_POINT_ACTION,
    CODE_TYPE_BADGE_CONTRIBUTION,
    CODE_TYPE_BADGE_LEARNING,
    CODE_TYPE_BADGE_QUIZ,
    CODE_TYPE_SESSION_TYPE,
    CODE_TYPE_SHEET_TYPE,
    CODE_TYPE_RECALL_DIRECTION,
)

# (code, code_name, mother_code, description, sort_order)
SEED_DATA = {
    CODE_TYPE_UI_THEME: [
        ("A", "Washi & Vermillion", None, "", 1),
        ("B", "Studio Mono", None, "", 2),
        ("C", "Genki Playful", None, "", 3),
    ],
    CODE_TYPE_SESSION_TYPE: [
        ("flashcard", "Flashcard", None, "Phiên học thẻ từ", 1),
        ("quiz", "Kiểm tra", None, "Phiên làm bài kiểm tra", 2),
    ],
    # SC10 — phiếu PDF. Mã dạng chữ để truy vấn tay còn đọc được, giống
    # session_type. Thêm một loại phiếu mới ở đây KHÔNG đủ: phải viết thêm hàm
    # vẽ tương ứng trong apps/practice_sheets/pdf_generator.py.
    CODE_TYPE_SHEET_TYPE: [
        ("writing", "Luyện viết ô kẻ", None, "Ô vuông kiểu genkoyoshi để tập viết tay", 1),
        ("recall", "Ôn lại từ", None, "Liệt kê từ và chừa chỗ trống để tự viết lại", 2),
    ],
    CODE_TYPE_RECALL_DIRECTION: [
        ("jp_vi", "Nhật → Việt", None, "Cho sẵn từ tiếng Nhật, chừa trống cách đọc và nghĩa", 1),
        ("vi_jp", "Việt → Nhật", None, "Cho sẵn nghĩa tiếng Việt, chừa trống từ và cách đọc", 2),
        ("mixed", "Trộn ngẫu nhiên", None, "Mỗi từ ngẫu nhiên một hướng trong cùng một phiếu", 3),
    ],
    CODE_TYPE_CONTRIBUTION_TYPE: [
        ("001", "Từ mới", None, "", 1),
        ("002", "Sửa nghĩa / cách dùng", None, "", 2),
        ("003", "Bình luận từ vựng", None, "", 3),
    ],
    CODE_TYPE_CONTRIBUTION_STATUS: [
        ("001", "Chờ duyệt", None, "", 1),
        ("002", "Đã duyệt", "DA_XU_LY", "", 2),
        ("003", "Từ chối", "DA_XU_LY", "", 3),
        ("DA_XU_LY", "Đã xử lý", None, "Code cha gom Đã duyệt + Từ chối, dùng để lọc/báo cáo", 0),
    ],
    CODE_TYPE_POINT_ACTION: [
        ("001", "Gửi góp ý từ mới", None, "+1 điểm", 1),
        ("002", "Từ mới được duyệt", None, "+10 điểm", 2),
        ("003", "Gửi sửa nghĩa/cách dùng", None, "+1 điểm", 3),
        ("004", "Sửa nghĩa được duyệt", None, "+5 điểm", 4),
        ("005", "Bình luận được duyệt", None, "+2 điểm", 5),
    ],
    # Mỗi nhóm danh hiệu bên dưới có 1 code_type riêng (yêu cầu: "badge riêng
    # nằm ở codeType riêng") — ngưỡng số (min_value) khai báo trong
    # apps.gamification.models.BadgeTier, ở đây chỉ là TÊN hiển thị.
    CODE_TYPE_BADGE_CONTRIBUTION: [
        ("001", "Tân Binh", None, "0 điểm đóng góp", 1),
        ("002", "Tích Cực", None, "50 điểm đóng góp", 2),
        ("003", "Chuyên Gia", None, "200 điểm đóng góp", 3),
        ("004", "Cố Vấn", None, "500 điểm đóng góp", 4),
        ("005", "Huyền Thoại", None, "1000 điểm đóng góp", 5),
    ],
    CODE_TYPE_BADGE_LEARNING: [
        ("001", "Người Mới Học", None, "50 từ đã thuộc", 1),
        ("002", "Chăm Chỉ", None, "200 từ đã thuộc", 2),
        ("003", "Ham Học Hỏi", None, "500 từ đã thuộc", 3),
        ("004", "Học Giả", None, "1000 từ đã thuộc", 4),
        ("005", "Bậc Thầy Từ Vựng", None, "2000 từ đã thuộc", 5),
    ],
    CODE_TYPE_BADGE_QUIZ: [
        ("001", "Khởi Động", None, "Đạt 1 bài kiểm tra >= 70%", 1),
        ("002", "Tay Vững", None, "Đạt 10 bài kiểm tra >= 80%", 2),
        ("003", "Thiện Xạ", None, "Đạt 30 bài kiểm tra >= 90%", 3),
        ("004", "Bất Bại", None, "Đạt 50 bài kiểm tra >= 95%", 4),
    ],
}


class Command(BaseCommand):
    help = "Seed dữ liệu MasterCode ban đầu (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--code-type", dest="code_type", default=None,
            help="Chỉ seed 1 code_type cụ thể (vd --code-type=05). Mặc định seed tất cả.",
        )

    def handle(self, *args, **options):
        from apps.core.models import MasterCode

        only = options.get("code_type")
        created, updated = 0, 0

        with transaction.atomic():
            for code_type, rows in SEED_DATA.items():
                if only and code_type != only:
                    continue
                for code, code_name, mother_code, description, sort_order in rows:
                    obj, was_created = MasterCode.objects.update_or_create(
                        code_type=code_type,
                        code=code,
                        defaults={
                            "code_name": code_name,
                            "mother_code": mother_code,
                            "description": description,
                            "sort_order": sort_order,
                        },
                    )
                    created += int(was_created)
                    updated += int(not was_created)

        self.stdout.write(self.style.SUCCESS(f"MasterCode seed xong — tạo mới {created}, cập nhật {updated}."))
