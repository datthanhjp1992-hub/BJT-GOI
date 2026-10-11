"""
Tham số nghiệp vụ của khu Kiểm tra — không phải danh sách lựa chọn hiển thị
(những thứ đó ở MasterCode, apps/core/constants.py code_type 20-23).
"""

# Bài từ vựng (S2): số câu được chọn và số từ tối thiểu để bắt đầu.
VOCAB_COUNTS = (10, 20, 30)
VOCAB_DEFAULT_COUNT = 20
VOCAB_MIN_WORDS = 4
OPTION_COUNT = 4

# Phạm vi bài từ vựng (scope["scope"]).
SCOPE_DUE = "due"            # từ đang nợ ôn hôm nay — câu đúng chấm như "Nhớ"
SCOPE_TOPICS = "topics"      # từ đã học trong các chủ đề chọn
SCOPE_MASTERED = "mastered"  # từ đã thuộc (hẹn ôn >= 21 ngày)
VOCAB_SCOPES = (SCOPE_DUE, SCOPE_TOPICS, SCOPE_MASTERED)

# Topic hàng kana (あ行, か行...) có slug đuôi "-line". Chúng phân loại theo chữ
# đầu cách đọc, không theo nghĩa -> không dùng làm nguồn đáp án nhiễu "cùng
# chủ đề" và không hiện ở danh sách chọn chủ đề của S2.
KANA_LINE_SLUG_SUFFIX = "-line"

# Chế độ Thi: thời lượng mỗi phần (phút). Chỉnh sau khi Dat thi thử thật (spec mục 1.3).
PART_MINUTES = {1: 50, 2: 35, 3: 40}

# S1 Tổng quan
RECENT_RESULTS = 5
WEAK_SPOT_DAYS = 30
WEAK_SPOT_MIN_ANSWERS = 5
WEAK_SPOT_COUNT = 3

# Sổ câu sai (◆4): ra khỏi sổ khi đúng liên tiếp ngần này lần, mỗi lần khác ngày.
WRONGBOOK_CLEAR_STREAK = 2
