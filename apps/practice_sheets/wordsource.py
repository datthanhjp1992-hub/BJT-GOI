"""
Đọc danh sách từ vựng mà người học tự tải lên (SC10).

Khác hẳn khu nhập dữ liệu SC07b: ở đây file **không ghi gì vào DB**. Người học
bất kỳ, không cần quyền admin, tải lên file của riêng mình và in ra phiếu —
bảng Vocabulary chung không bị đụng tới. Kết quả đọc ra là `WordItem` thuần
Python, view cất vào `PracticeSheet.custom_words` để còn tải lại PDF cũ.

Dùng chung `apps.core.dataio.read_table` nên được miễn phí: đọc cả .csv/.xlsx/
.xlsm, tự dò bảng mã utf-8-sig → cp932 → utf-8, bỏ dòng trống cuối file, và xử
lý đúng ô có dấu phẩy / dấu nháy / xuống dòng theo chuẩn RFC 4180.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from apps.core.dataio import DataFileError, read_table

# Một phiếu 300 từ đã là ~40 trang A4. Trên mức đó thì vẽ rất lâu và người ta
# cũng không in. Giới hạn này CHẶT HƠN dataio.MAX_IMPORT_ROWS (2000) vì ở đây
# mỗi dòng còn phải vẽ ra hình, không chỉ ghi một row DB.
MAX_WORDS_PER_SHEET = 300

# Tối đa cho mỗi ô, cắt bớt thay vì báo lỗi: phiếu in ra không chứa nổi câu dài.
MAX_WORD_LEN = 100
MAX_READING_LEN = 150
MAX_MEANING_LEN = 255


@dataclass(frozen=True)
class WordItem:
    """Một từ để vẽ lên phiếu. Cố tình KHÔNG phải model.

    Nhờ vậy cùng một hàm vẽ PDF dùng được cho cả từ trong DB lẫn từ trong file
    người dùng vừa tải lên. `Vocabulary` cũng có đủ ba thuộc tính này nên chỗ
    nào đang truyền thẳng Vocabulary vẫn chạy.
    """

    word: str
    reading: str = ""
    meaning_vi: str = ""

    @classmethod
    def from_vocabulary(cls, vocabulary):
        return cls(
            word=vocabulary.word,
            reading=vocabulary.reading or "",
            meaning_vi=vocabulary.meaning_vi or "",
        )

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            word=str(data.get("word", "")).strip(),
            reading=str(data.get("reading", "") or "").strip(),
            meaning_vi=str(data.get("meaning_vi", "") or "").strip(),
        )

    def as_dict(self):
        return {"word": self.word, "reading": self.reading, "meaning_vi": self.meaning_vi}


def _normalize_header(text):
    """'Nghĩa tiếng Việt' và 'nghia_tieng_viet' phải khớp nhau.

    Bỏ dấu tiếng Việt (NFD rồi loại ký tự tổ hợp), hạ chữ thường, đổi mọi dấu
    ngăn cách thành khoảng trắng đơn. Người dùng gõ lại tiêu đề bằng tay hay
    thiếu dấu là chuyện thường; bắt gõ đúng từng ký tự thì không ai nhập nổi.
    """
    text = unicodedata.normalize("NFD", str(text or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    for ch in "_-./|":
        text = text.replace(ch, " ")
    return " ".join(text.split())


# Tiêu đề chấp nhận được -> tên field. Gồm cả bộ cột chuẩn của SC07b
# (word/reading/meaning_vi) để file xuất từ màn quản trị dùng lại được ngay,
# lẫn cách gọi tiếng Việt và tiếng Nhật cho người tự gõ file.
HEADER_ALIASES = {
    "word": "word",
    "tu": "word",
    "tu vung": "word",
    "tu moi": "word",
    "kanji": "word",
    "kanji kana": "word",
    "表記": "word",
    "単語": "word",
    "reading": "reading",
    "cach doc": "reading",
    "phien am": "reading",
    "furigana": "reading",
    "kana": "reading",
    "よみ": "reading",
    "読み": "reading",
    "ふりがな": "reading",
    "meaning vi": "meaning_vi",
    "meaning": "meaning_vi",
    "nghia": "meaning_vi",
    "nghia tieng viet": "meaning_vi",
    "y nghia": "meaning_vi",
    "意味": "meaning_vi",
}


def _map_headers(headers):
    """{tên field: vị trí cột}. Cột lạ bị bỏ qua, không phải lỗi."""
    mapping = {}
    for position, raw in enumerate(headers):
        field = HEADER_ALIASES.get(_normalize_header(raw))
        if field and field not in mapping:
            mapping[field] = position
    return mapping


def _cell(row, position):
    if position is None or position >= len(row):
        return ""
    value = row[position]
    if value is None:
        return ""
    return str(value).strip()


def parse_word_file(raw, filename):
    """(items, skipped_rows) từ nội dung file người dùng tải lên.

    Ném `DataFileError` khi cả file không dùng được (sai định dạng, không có
    cột từ vựng, quá số dòng). Dòng lẻ bị thiếu từ thì chỉ BỎ QUA và đếm vào
    `skipped_rows` — bắt người ta sửa cả file chỉ vì một dòng trống thừa là quá
    khắt khe cho một thao tác chỉ để in giấy.
    """
    headers, rows = read_table(raw, filename)
    mapping = _map_headers(headers)

    if "word" not in mapping:
        raise DataFileError(
            "practice_sheets.upload.error.missing_required_column", column_name="word"
        )
    if len(rows) > MAX_WORDS_PER_SHEET:
        raise DataFileError(
            "practice_sheets.upload.error.too_many_words",
            max_words=MAX_WORDS_PER_SHEET,
            word_count=len(rows),
        )

    items = []
    skipped = 0
    seen = set()
    for row in rows:
        word = _cell(row, mapping.get("word"))[:MAX_WORD_LEN]
        if not word:
            skipped += 1
            continue
        reading = _cell(row, mapping.get("reading"))[:MAX_READING_LEN]
        meaning = _cell(row, mapping.get("meaning_vi"))[:MAX_MEANING_LEN]
        # Trùng (từ, cách đọc) trong cùng một file thì in hai lần vô nghĩa.
        signature = (word, reading)
        if signature in seen:
            skipped += 1
            continue
        seen.add(signature)
        items.append(WordItem(word=word, reading=reading, meaning_vi=meaning))

    if not items:
        raise DataFileError("practice_sheets.upload.error.empty_file")
    return items, skipped


def template_headers():
    """Bộ cột của file mẫu tải về ở màn SC10.

    Cố ý trùng ba cột đầu của mẫu gộp bên SC07b (`vocabulary.vocabulary_full`)
    nên file xuất từ màn quản trị dùng thẳng được ở đây, không phải sửa tiêu đề.
    """
    return ["word", "reading", "meaning_vi"]
