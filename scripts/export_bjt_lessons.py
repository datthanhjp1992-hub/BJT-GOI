"""
Xuất khung bài + 3 dạng luyện tập Quyển 1 từ bjt.db (BJT-WEB) ra CSV — docs/SPEC_LUYEN_TAP_BAI.md T2.

    python scripts/export_bjt_lessons.py ../BJT-WEB/data/bjt.db

Ghi 8 file docs/data/lessons/01_unit.csv ... 08_politeness_phrase.csv. Header đúng bằng
header của màn Nhập/xuất dữ liệu (SC07b), nạp theo thứ tự số file, chế độ upsert.
bjt.db chỉ cần lúc xuất; CSV trong repo là nguồn.

Biến đổi duy nhất: drills.example_jp "A → B" tách thành example_prompt_jp / example_answer_jp.
Mọi thứ khác chép nguyên (strip khoảng trắng), kể cả {1} {2} trong lời thoại đóng vai.
"""
import csv
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "docs" / "data" / "lessons"
ARROW = " → "

# (tên file, header, câu SQL trả cột ĐÚNG thứ tự header). units.id == units.position
# nên unit_id của lessons/reviews dùng thẳng làm Unit.number.
FILES = [
    ("01_unit.csv", ["number", "name_jp", "name_vi"],
     "select position, name_jp, name_vi from units order by position"),
    ("02_lesson.csv", ["unit__number", "scene_no", "title_jp", "title_vi", "situation_vi"],
     "select u.position, l.scene_no, l.title_jp, l.title_vi, l.situation_vi "
     "from lessons l join units u on u.id = l.unit_id order by l.scene_no"),
    ("03_drill.csv", ["lesson__scene_no", "example_prompt_jp", "example_answer_jp"],
     "select l.scene_no, d.example_jp, null from drills d join lessons l on l.id = d.lesson_id order by l.scene_no"),
    ("04_drill_item.csv", ["drill__lesson__scene_no", "number", "prompt_jp", "answer_jp"],
     "select l.scene_no, i.item_no, i.prompt_jp, i.answer_jp from drill_items i "
     "join drills d on d.id = i.drill_id join lessons l on l.id = d.lesson_id order by l.scene_no, i.item_no"),
    ("05_roleplay.csv", ["unit__number", "number", "situation_vi", "book_page"],
     "select u.position, r.review_no, r.situation_vi, r.book_page from reviews r "
     "join units u on u.id = r.unit_id order by u.position, r.review_no"),
    ("06_roleplay_line.csv", ["roleplay__unit__number", "roleplay__number", "number", "speaker", "text_jp"],
     "select u.position, r.review_no, x.line_no, x.speaker, x.text_jp from review_lines x "
     "join reviews r on r.id = x.review_id join units u on u.id = r.unit_id order by u.position, r.review_no, x.line_no"),
    ("07_roleplay_blank.csv", ["roleplay__unit__number", "roleplay__number", "number", "answer_jp"],
     "select u.position, r.review_no, a.blank_no, a.answer_jp from review_answers a "
     "join reviews r on r.id = a.review_id join units u on u.id = r.unit_id order by u.position, r.review_no, a.blank_no"),
    ("08_politeness_phrase.csv", ["lesson__scene_no", "phrase_jp", "level_code"],
     "select l.scene_no, f.phrase_jp, f.formality from formal_informal f "
     "join lessons l on l.id = f.lesson_id order by l.scene_no, f.formality, f.id"),
]


def clean(value):
    return "" if value is None else str(value).strip()


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, header, sql in FILES:
        rows = [[clean(v) for v in row] for row in con.execute(sql)]
        if name == "03_drill.csv":
            for row in rows:
                parts = row[1].split(ARROW)
                if len(parts) != 2:
                    sys.exit(f"Câu mẫu bài {row[0]} không có đúng một '{ARROW.strip()}': {row[1]}")
                row[1], row[2] = parts[0].strip(), parts[1].strip()
        with open(OUT_DIR / name, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        print(f"{len(rows):4} dòng -> {(OUT_DIR / name).relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
