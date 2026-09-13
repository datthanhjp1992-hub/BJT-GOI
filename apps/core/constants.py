"""
CODE_TYPE registry for MasterCode.

Toàn bộ danh sách lựa chọn hiển thị trước đây định nghĩa cứng bằng
`choices=[...]` (BJT level, UI theme, ...) nay chuyển sang bảng MasterCode
(apps.core.models.MasterCode) — file này chỉ còn giữ lại các hằng số
`code_type` (để không rải "05", "06"... dạng magic string khắp nơi) và vài
hàm tiện lấy choices động cho Django (`choices=` chấp nhận callable).

Không thêm `choices=[("J5", "..."), ...]` cứng ở đây hay ở model nào khác nữa
— nếu cần thêm 1 danh sách lựa chọn mới, tạo `code_type` mới, seed dữ liệu
trong `apps/core/management/commands/seed_mastercode.py`, rồi dùng
`apps.core.mastercode.get_choices(CODE_TYPE_XXX)`.
"""
from apps.core.mastercode import get_choices

# --- Nội dung học tập ---
CODE_TYPE_BJT_LEVEL = "05"       # J5, J4, J3, J2, J1, J1+
CODE_TYPE_UI_THEME = "06"        # A, B, C (Washi & Vermillion / Studio Mono / Genki Playful)
CODE_TYPE_SESSION_TYPE = "09"    # flashcard, quiz (kieu phien hoc)

# --- Góp ý & kiểm duyệt (xem docs/SPEC_GOP_Y_THANH_TICH.md) ---
CODE_TYPE_CONTRIBUTION_TYPE = "02"    # Từ mới / Sửa nghĩa / Bình luận
CODE_TYPE_CONTRIBUTION_STATUS = "03"  # Chờ duyệt / Đã duyệt / Từ chối
CODE_TYPE_POINT_ACTION = "04"         # Loại hành động cộng điểm

# --- Danh hiệu (mỗi NHÓM danh hiệu có 1 code_type riêng — xem BadgeCategory) ---
CODE_TYPE_BADGE_CONTRIBUTION = "01"   # Danh hiệu theo điểm đóng góp (Tân Binh -> Huyền Thoại)
CODE_TYPE_BADGE_LEARNING = "07"       # Danh hiệu theo số từ đã học thuộc
CODE_TYPE_BADGE_QUIZ = "08"           # Danh hiệu theo kết quả kiểm tra

# code_type dành cho danh hiệu do BadgeCategory quản lý động, không hardcode
# thêm ở đây nữa — thêm category mới = thêm 1 row BadgeCategory + seed code_type
# tương ứng, xem apps/gamification/models.py.


def bjt_level_choices():
    """Dùng cho `choices=bjt_level_choices` trên field CharField (callable)."""
    return get_choices(CODE_TYPE_BJT_LEVEL)


def ui_theme_choices():
    return get_choices(CODE_TYPE_UI_THEME)


def session_type_choices():
    """Kiểu phiên học. Mã giữ nguyên dạng chữ ("flashcard"/"quiz") thay vì
    "001"/"002" để code cũ lọc `session_type="quiz"` vẫn chạy, và để truy vấn
    tay trên Supabase còn đọc được."""
    return get_choices(CODE_TYPE_SESSION_TYPE)
