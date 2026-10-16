"""Nhập docs/data/grammar/grammar_pattern.csv — idempotent theo `pattern`."""
import csv

from .models import GrammarPattern

FIELDS = ["meaning_vi", "connection_form", "example_jp", "example_vi", "level", "category", "note"]


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def validate(rows):
    """Danh sách (số dòng, lỗi). Dòng 1 là tiêu đề nên dữ liệu bắt đầu từ 2."""
    errors, seen = [], set()
    for i, r in enumerate(rows, start=2):
        p = (r.get("pattern") or "").strip()
        if not p or not (r.get("meaning_vi") or "").strip():
            errors.append((i, "thiếu pattern hoặc meaning_vi"))
        elif p in seen:
            errors.append((i, f"trùng pattern {p}"))
        seen.add(p)
    return errors


def apply_rows(rows):
    """Tạo mới / cập nhật theo pattern; thứ tự dòng trong file = display_order. Trả (new, updated, same)."""
    existing = {g.pattern: g for g in GrammarPattern.objects.all()}
    new = updated = same = 0
    for order, r in enumerate(rows, start=1):
        values = {k: (r.get(k) or "").strip() for k in FIELDS}
        values["display_order"] = order
        obj = existing.get(r["pattern"].strip())
        if obj is None:
            GrammarPattern.objects.create(pattern=r["pattern"].strip(), **values)
            new += 1
        elif any(getattr(obj, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(obj, k, v)
            obj.save()
            updated += 1
        else:
            same += 1
    return new, updated, same
