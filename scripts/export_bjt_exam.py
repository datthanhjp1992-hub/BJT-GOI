"""
Xuất 500 câu đề thi thử từ bjt.db (BJT-WEB) ra CSV trong repo — docs/SPEC_KIEM_TRA.md T7.2.

    python scripts/export_bjt_exam.py ../BJT-WEB/data/bjt.db

Ghi docs/data/exam/exam_question.csv — MỘT dòng một câu, 4 phương án nằm ngay trên dòng
(option_1..option_4 + correct) để soát bằng Excel dễ hơn 3 file nối nhau. File này là
nguồn để scripts/import_exam.py đẩy lên Supabase; bjt.db chỉ cần lúc xuất.

Quy ước:
  - section_code = p<part>s<section> (MasterCode 20).
  - number = thứ tự trong bộ đề, sắp theo (part, section, id) -> 1..100.
  - audio_path = mock/<tên file>  (đường dẫn trong bucket exam-audio, spec mục 0.3).
  - source_ref = bjt.db:mock_exam_question:<id>  (khoá idempotent khi import).
"""
import csv
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "docs" / "data" / "exam" / "exam_question.csv"
AUDIO_PREFIX = "mock/"

COLUMNS = [
    "source_ref", "exam_set", "number", "part", "section_code", "passage_type", "passage_jp",
    "stem_jp", "option_1", "option_2", "option_3", "option_4", "correct", "explanation_vi",
    "level", "audio_path", "source_note",
]


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
    rows = con.execute(
        "select id, exam_set, part, section, passage_type, passage_jp, question_jp, choice_1, choice_2, "
        "choice_3, choice_4, correct_choice, explanation_vi, level, audio_file, source_file "
        "from mock_exam_question order by exam_set, part, section, id"
    ).fetchall()

    out, numbers = [], {}
    for (qid, exam_set, part, section, ptype, passage, stem, c1, c2, c3, c4, correct, expl,
         level, audio, source) in rows:
        numbers[exam_set] = numbers.get(exam_set, 0) + 1
        out.append({
            "source_ref": f"bjt.db:mock_exam_question:{qid}",
            "exam_set": exam_set,
            "number": numbers[exam_set],
            "part": part,
            "section_code": f"p{part}s{section}",
            "passage_type": (ptype or "").strip(),
            "passage_jp": (passage or "").strip(),
            "stem_jp": (stem or "").strip(),
            "option_1": c1.strip(), "option_2": c2.strip(), "option_3": c3.strip(), "option_4": c4.strip(),
            "correct": correct,
            "explanation_vi": (expl or "").strip(),
            "level": level or "",
            "audio_path": AUDIO_PREFIX + Path(audio).name if audio else "",
            "source_note": source or "",
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(out)
    print(f"{len(out)} câu -> {OUT.relative_to(BASE_DIR)}")
    for s, n in sorted(numbers.items()):
        print(f"  Bộ đề {s}: {n} câu")


if __name__ == "__main__":
    main()
