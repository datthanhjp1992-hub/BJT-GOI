"""
Nhập đề thi thử từ docs/data/exam/exam_question.csv — docs/SPEC_KIEM_TRA.md T7.2.

Logic nằm ở đây (test được), scripts/import_exam.py chỉ là lớp vỏ dòng lệnh.

Idempotent theo source_ref: chạy lại cùng file -> 0 thay đổi. Câu đã có thì CẬP NHẬT
nội dung theo CSV nhưng giữ nguyên is_active (admin tắt câu lỗi thì import lại không
bật lên) và audio_version (do scripts/upload_exam_audio.py quản lý).
"""
import csv
from collections import Counter
from dataclasses import dataclass, field

from django.db import transaction

from .models import ExamOption, ExamQuestion, ExamSet

OPTION_COUNT = 4
SECTION_CODES = {"p1s1", "p1s2", "p1s3", "p2s1", "p2s2", "p3s1", "p3s2", "p3s3"}
QUESTION_FIELDS = ("number", "part", "section_code", "passage_type", "passage_jp", "stem_jp",
                   "explanation_vi", "level", "audio_path")


@dataclass
class ImportStats:
    sets_new: int = 0
    new: int = 0
    updated: int = 0
    same: int = 0
    errors: list = field(default_factory=list)


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def validate(rows):
    """Lỗi chặn import: [(số dòng CSV, thông báo)]. Rỗng = hợp lệ."""
    errors, refs, numbers = [], Counter(), Counter()
    for line, row in enumerate(rows, start=2):
        def bad(msg):
            errors.append((line, msg))
        if not row.get("source_ref"):
            bad("thiếu source_ref")
        refs[row.get("source_ref")] += 1
        numbers[(row.get("exam_set"), row.get("number"))] += 1
        if row.get("section_code") not in SECTION_CODES:
            bad(f"section_code '{row.get('section_code')}' không hợp lệ")
        elif row.get("section_code", "")[1:2] != str(row.get("part")):
            bad("part không khớp section_code")
        if not (row.get("stem_jp") or "").strip():
            bad("thiếu stem_jp")
        options = [(row.get(f"option_{i}") or "").strip() for i in range(1, OPTION_COUNT + 1)]
        if not all(options):
            bad("thiếu phương án")
        elif len(set(options)) != OPTION_COUNT:
            bad("có phương án trùng nhau")
        if row.get("correct") not in {str(i) for i in range(1, OPTION_COUNT + 1)}:
            bad(f"correct '{row.get('correct')}' phải là 1-{OPTION_COUNT}")
        for key in ("exam_set", "number", "part"):
            if not str(row.get(key, "")).isdigit():
                bad(f"{key} phải là số")
    errors += [(0, f"source_ref trùng: {r}") for r, n in refs.items() if n > 1]
    errors += [(0, f"bộ đề {s} có 2 câu số {n}") for (s, n), c in numbers.items() if c > 1]
    return errors


def _question_values(row, exam_set):
    return {
        "exam_set": exam_set,
        "number": int(row["number"]),
        "part": int(row["part"]),
        "section_code": row["section_code"],
        "passage_type": row.get("passage_type") or "",
        "passage_jp": row.get("passage_jp") or "",
        "stem_jp": row["stem_jp"],
        "explanation_vi": row.get("explanation_vi") or "",
        "level": row.get("level") or "",
        "audio_path": row.get("audio_path") or "",
    }


@transaction.atomic
def apply_rows(rows):
    """Ghi vào DB. Gọi validate() trước — hàm này giả định dữ liệu đã hợp lệ."""
    stats = ImportStats()
    sets = {s.number: s for s in ExamSet.objects.all()}
    for number in sorted({int(r["exam_set"]) for r in rows}):
        if number not in sets:
            sets[number] = ExamSet.objects.create(number=number, title=f"Bộ đề {number}", slug=f"bo-de-{number}",
                                                  source_note="bjt.db mock_exam_question")
            stats.sets_new += 1

    existing = {q.source_ref: q for q in ExamQuestion.objects.prefetch_related("options")}
    # Đổi số câu có thể đụng unique (exam_set, number) giữa chừng -> dời tạm số của câu sắp
    # đổi ra vùng 1000+ trước, rồi mới ghi số thật.
    moving = [existing[r["source_ref"]] for r in rows if r["source_ref"] in existing
              and existing[r["source_ref"]].number != int(r["number"])]
    for q in moving:
        ExamQuestion.objects.filter(pk=q.pk).update(number=1000 + q.pk)

    for row in rows:
        values = _question_values(row, sets[int(row["exam_set"])])
        correct = int(row["correct"])
        options = [(i, row[f"option_{i}"].strip(), i == correct) for i in range(1, OPTION_COUNT + 1)]
        q = existing.get(row["source_ref"])
        if q is None:
            q = ExamQuestion(source_ref=row["source_ref"], **values)
            q.save()
            for pos, text, ok in options:
                ExamOption(question=q, position=pos, text_jp=text, is_correct=ok).save()
            stats.new += 1
            continue

        changed = q in moving
        for key, value in values.items():
            current = q.exam_set_id if key == "exam_set" else getattr(q, key)
            target = value.pk if key == "exam_set" else value
            if current != target:
                setattr(q, key, value)
                changed = True
        if changed:
            q.save()
        by_pos = {o.position: o for o in q.options.all()}
        for pos, text, ok in options:
            opt = by_pos.get(pos)
            if opt is None:
                ExamOption(question=q, position=pos, text_jp=text, is_correct=ok).save()
                changed = True
            elif (opt.text_jp, opt.is_correct) != (text, ok):
                opt.text_jp, opt.is_correct = text, ok
                opt.save()
                changed = True
        if changed:
            stats.updated += 1
        else:
            stats.same += 1
    return stats


def check_database():
    """Soát dữ liệu đề đang có trong DB (lệnh check_exam_data). Trả về list lỗi chuỗi."""
    problems = []
    expected = Counter({"p1s1": 10, "p1s2": 10, "p1s3": 15, "p2s1": 15, "p2s2": 15,
                        "p3s1": 15, "p3s2": 10, "p3s3": 10})
    listening = {"p1s1", "p1s2", "p1s3", "p2s1"}
    for exam_set in ExamSet.objects.prefetch_related("questions__options"):
        counts = Counter()
        for q in exam_set.questions.all():
            if not q.is_active:
                continue
            counts[q.section_code] += 1
            opts = list(q.options.all())
            if len(opts) != OPTION_COUNT:
                problems.append(f"{exam_set.title} câu {q.number}: {len(opts)} phương án")
            if sum(o.is_correct for o in opts) != 1:
                problems.append(f"{exam_set.title} câu {q.number}: số đáp án đúng = {sum(o.is_correct for o in opts)}")
            if q.section_code in listening and not q.audio_path:
                problems.append(f"{exam_set.title} câu {q.number}: câu nghe thiếu audio_path")
        if counts != expected:
            problems.append(f"{exam_set.title}: số câu theo dạng {dict(counts)} khác chuẩn {dict(expected)}")
    return problems
