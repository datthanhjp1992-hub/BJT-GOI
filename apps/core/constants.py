"""
CODE_TYPE registry for MasterCode.

Toàn bộ danh sách lựa chọn hiển thị trước đây định nghĩa cứng bằng
`choices=[...]` (UI theme, kiểu phiên học, ...) nay chuyển sang bảng MasterCode
(apps.core.models.MasterCode) — file này chỉ còn giữ lại các hằng số
`code_type` (để không rải "05", "06"... dạng magic string khắp nơi) và vài
hàm tiện lấy choices động cho Django (`choices=` chấp nhận callable).

Không thêm `choices=[("A", "..."), ...]` cứng ở đây hay ở model nào khác nữa
— nếu cần thêm 1 danh sách lựa chọn mới, tạo `code_type` mới, seed dữ liệu
trong `apps/core/management/commands/seed_mastercode.py`, rồi dùng
`apps.core.mastercode.get_choices(CODE_TYPE_XXX)`.
"""
from apps.core.mastercode import get_choices

# --- Nội dung học tập ---
# code_type "05" TRỐNG: trước đây là cấp độ BJT (J5..J1+). Bỏ ngày 13/09/2026 —
# từ vựng phân loại theo CHỦ ĐỀ (vocabulary.Topic), không theo cấp độ nữa. Đừng
# tái sử dụng "05" cho thứ khác, dữ liệu cũ trên Supabase có thể còn sót row.
CODE_TYPE_UI_THEME = "06"        # A, B, C (Washi & Vermillion / Studio Mono / Genki Playful)
CODE_TYPE_SESSION_TYPE = "09"    # flashcard, quiz (kieu phien hoc)

# Giá trị thật của CODE_TYPE_SESSION_TYPE, dùng khi tạo StudySession (xem
# apps.learning.views.flashcard_view) — cùng cách đặt hằng số như SHEET_TYPE_*
# bên dưới, để không rải chuỗi "flashcard" khắp views/services.
SESSION_TYPE_FLASHCARD = "flashcard"
SESSION_TYPE_QUIZ = "quiz"

# --- Phiếu luyện tập in ra PDF (SC10) ---
CODE_TYPE_SHEET_TYPE = "10"       # writing, recall (loai phieu)
CODE_TYPE_RECALL_DIRECTION = "11"  # jp_vi, vi_jp, mixed (huong on tap)

# Mã cụ thể của hai code_type trên. Đây KHÔNG phải danh sách choices hardcode
# (danh sách vẫn nằm trong MasterCode) — chỉ là hằng số để code khỏi rải chuỗi
# "writing"/"vi_jp" khắp nơi, giống CONTRIBUTION_STATUS_PENDING bên admin_panel.
SHEET_TYPE_WRITING = "writing"
SHEET_TYPE_RECALL = "recall"
RECALL_JP_TO_VI = "jp_vi"
RECALL_VI_TO_JP = "vi_jp"
RECALL_MIXED = "mixed"

# --- Góp ý & kiểm duyệt (xem docs/SPEC_GOP_Y_THANH_TICH.md) ---
CODE_TYPE_CONTRIBUTION_TYPE = "02"    # Từ mới / Sửa nghĩa / Bình luận
CODE_TYPE_CONTRIBUTION_STATUS = "03"  # Chờ duyệt / Đã duyệt / Từ chối
CODE_TYPE_POINT_ACTION = "04"         # Loại hành động cộng điểm

# --- Báo cáo lỗi nội dung (màn "Báo cáo lỗi" trong khu quản trị) ---
# Tách hẳn khỏi Góp ý (code_type 02/03): góp ý là ĐỀ XUẤT thêm/sửa nội dung và
# có cộng điểm; báo lỗi là BÁO HỎNG ("từ này sai cách đọc", "trang này vỡ"),
# không cộng điểm, vòng đời chỉ có xử lý xong hay bỏ qua.
CODE_TYPE_ERROR_TYPE = "12"      # Loại lỗi bị báo
CODE_TYPE_ERROR_STATUS = "13"    # Trạng thái xử lý báo lỗi

# Mã cụ thể của CODE_TYPE_ERROR_STATUS — hằng số để không rải "001"/"002"
# trong truy vấn, giống CONTRIBUTION_STATUS_PENDING bên apps/admin_panel.
ERROR_STATUS_PENDING = "001"    # Chờ xử lý
ERROR_STATUS_FIXED = "002"      # Đã sửa
ERROR_STATUS_DISMISSED = "003"  # Bỏ qua
ERROR_STATUS_HANDLED_PARENT = "DA_XU_LY"  # mother_code gom 002 + 003

# --- Danh hiệu (mỗi NHÓM danh hiệu có 1 code_type riêng — xem BadgeCategory) ---
CODE_TYPE_BADGE_CONTRIBUTION = "01"   # Danh hiệu theo điểm đóng góp (Tân Binh -> Huyền Thoại)
CODE_TYPE_BADGE_LEARNING = "07"       # Danh hiệu theo số từ đã học thuộc
CODE_TYPE_BADGE_QUIZ = "08"           # Danh hiệu theo kết quả kiểm tra

# code_type dành cho danh hiệu do BadgeCategory quản lý động, không hardcode
# thêm ở đây nữa — thêm category mới = thêm 1 row BadgeCategory + seed code_type
# tương ứng, xem apps/gamification/models.py.


def bjt_level_choices():
    """ĐÃ BỎ — cấp độ BJT không còn là cách phân loại từ vựng (13/09/2026).

    Hàm phải TỒN TẠI, không được xoá: `accounts/0001_initial.py` và
    `vocabulary/0001_initial.py` tham chiếu thẳng tới nó, mà migration cũ thì
    Django vẫn import mỗi lần dựng đồ thị migration. Xoá hàm này = mọi lệnh
    manage.py chết với AttributeError.

    Trả rỗng vì code_type "05" không còn được seed. ĐỪNG dùng cho field mới.
    """
    return []


def ui_theme_choices():
    return get_choices(CODE_TYPE_UI_THEME)


def session_type_choices():
    """Kiểu phiên học. Mã giữ nguyên dạng chữ ("flashcard"/"quiz") thay vì
    "001"/"002" để code cũ lọc `session_type="quiz"` vẫn chạy, và để truy vấn
    tay trên Supabase còn đọc được."""
    return get_choices(CODE_TYPE_SESSION_TYPE)


def sheet_type_choices():
    """Loại phiếu PDF: ô kẻ luyện viết / phiếu ôn lại từ. Mã dạng chữ như
    session_type để đọc được khi truy vấn tay."""
    return get_choices(CODE_TYPE_SHEET_TYPE)


def recall_direction_choices():
    """Hướng ôn tập của phiếu 'ôn lại từ' — chỉ có nghĩa khi
    sheet_type = SHEET_TYPE_RECALL."""
    return get_choices(CODE_TYPE_RECALL_DIRECTION)


def error_type_choices():
    """Loại lỗi người dùng chọn khi báo lỗi một từ vựng (sai nghĩa, sai cách
    đọc, sai ví dụ...). Thuần dữ liệu hiển thị — thêm loại mới = thêm 1 dòng
    trong seed_mastercode.py, KHÔNG phải sửa code."""
    return get_choices(CODE_TYPE_ERROR_TYPE)


def error_status_choices(include_parent=False):
    """Trạng thái xử lý báo lỗi. Mặc định bỏ code cha "DA_XU_LY" — nó chỉ dùng
    để gom nhóm khi lọc/thống kê, không bao giờ là trạng thái thật của một bản
    ghi, nên không được xuất hiện trong <select>."""
    rows = get_choices(CODE_TYPE_ERROR_STATUS)
    if include_parent:
        return rows
    return [(code, name) for code, name in rows if code != ERROR_STATUS_HANDLED_PARENT]


# --- Kính ngữ (app apps.keigo) ---
# Ba code_type mới cho khu kính ngữ. Giống mọi nhóm khác: KHÔNG hardcode
# choices=[...] ở model, mà khai code_type ở đây rồi seed trong
# seed_mastercode.py và đọc qua get_choices().
CODE_TYPE_KEIGO_STYLE = "14"      # Loại kính ngữ
CODE_TYPE_KEIGO_PAIR_TYPE = "15"  # Loại cặp từ (8 bảng của trang 11, 17-21)
CODE_TYPE_QUESTION_TYPE = "16"    # Dạng câu hỏi trắc nghiệm

# Mã cụ thể — hằng số để code khỏi rải chuỗi, giống SHEET_TYPE_* / SESSION_TYPE_*.
#
# LƯU Ý về kenjo/kenjo1/kenjo2: sách chỉ phân 謙譲語 I và II ở ĐÚNG hai bảng nhỏ
# trang 7. Bảng chia động từ trang 13-16 chỉ có MỘT cột 謙譲語 chung, nên phải có
# mã `kenjo` không phân cấp. Đừng suy đoán I/II cho những dòng sách không nói.
KEIGO_STYLE_SONKEI = "sonkei"
KEIGO_STYLE_KENJO = "kenjo"
KEIGO_STYLE_KENJO1 = "kenjo1"
KEIGO_STYLE_KENJO2 = "kenjo2"
KEIGO_STYLE_TEINEI = "teinei"
KEIGO_STYLE_BIKAGO = "bikago"
KEIGO_STYLE_JUJU = "juju"

QUESTION_TYPE_MCQ = "mcq_blank"
QUESTION_TYPE_ORDERING = "ordering"
QUESTION_TYPE_CLOZE = "cloze"

# Kiểu phiên học mới của code_type "09" — để lượt làm bài kính ngữ cũng ghi một
# learning.StudySession, nhờ đó streak và biểu đồ lịch sử ở dashboard/SC15 tự
# đếm luôn phần kính ngữ mà không phải sửa gamification/services.py.
SESSION_TYPE_KEIGO = "keigo"


def keigo_style_choices():
    """Loại kính ngữ: 尊敬語 / 謙譲語 (chung, I, II) / 丁寧語 / 美化語 / cho-nhận."""
    return get_choices(CODE_TYPE_KEIGO_STYLE)


def keigo_pair_type_choices():
    """Loại cặp từ trong KeigoPhrasePair — mỗi mã là một bảng trong sách."""
    return get_choices(CODE_TYPE_KEIGO_PAIR_TYPE)


def question_type_choices():
    """Dạng câu hỏi. Đặt ở CẤP CÂU chứ không phải cấp bộ đề: BÀI TẬP 6 và 8
    trộn câu sắp xếp ★ vào giữa bộ đề điền (  )."""
    return get_choices(CODE_TYPE_QUESTION_TYPE)
