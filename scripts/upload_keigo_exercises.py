"""
Đẩy bộ đề kính ngữ (4 file CSV 07-10) lên Supabase.

Dùng thẳng engine nhập dữ liệu SC07b (apps.core.dataio): cùng khoá tự nhiên,
cùng full_clean() từng dòng (kể cả phép kiểm ★ của Question), cùng audit.

    # 1. chạy thử — nạp cả 4 file trong transaction rồi ROLLBACK, không ghi gì
    python scripts/upload_keigo_exercises.py docs/data/keigo/tu_soan

    # 2. ghi thật, người tạo là tài khoản dat
    python scripts/upload_keigo_exercises.py docs/data/keigo/tu_soan --apply --as-user dat

Chế độ mặc định `upsert`: câu đã có (theo code) được ghi đè -> sửa lời giải
trong CSV rồi chạy lại là cập nhật. Không xoá gì: câu bị bỏ khỏi CSV vẫn nằm trên DB.

Phải nạp lần lượt TRONG CÙNG transaction: file 08 tham chiếu bộ đề của file 07,
nên khi chạy thử, file 07 cũng phải được ghi tạm thì file 08 mới dò ra khoá ngoại.
Có lỗi ở bất kỳ file nào -> rollback cả 4.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _vocab_common import DIM, GREEN, RED, RESET, YELLOW, DryRun, act_as, say, setup_django

# (file, bảng) — đúng thứ tự phụ thuộc khoá ngoại.
FILES = (
    ("07_exercise_set.csv", "keigo.exerciseset"),
    ("08_exercise_section.csv", "keigo.exercisesection"),
    ("09_question.csv", "keigo.question"),
    ("10_question_option.csv", "keigo.questionoption"),
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Đẩy bộ đề kính ngữ (CSV 07-10) lên Supabase.")
    ap.add_argument("folder", type=Path, help="Thư mục chứa 4 file 07_..10_.")
    ap.add_argument("--apply", action="store_true", help="Ghi thật. Không có cờ này thì chỉ chạy thử.")
    ap.add_argument("--mode", default="upsert", choices=("insert", "upsert", "update"),
                    help="insert = chỉ thêm mới; upsert (mặc định) = thêm + ghi đè; update = chỉ ghi đè.")
    ap.add_argument("--as-user", metavar="USERNAME", help="Ghi created_by/updated_by là user này.")
    ap.add_argument("--settings", default="config.settings.supabase",
                    help="Django settings (mặc định config.settings.supabase).")
    args = ap.parse_args()

    missing = [name for name, _ in FILES if not (args.folder / name).is_file()]
    if missing:
        say(RED, "LỖI", f"Thiếu file trong {args.folder}: {', '.join(missing)}")
        sys.exit(1)

    setup_django(args.settings)
    from django.db import transaction

    from apps.core.dataio import DataFileError, get_dataset, read_table

    say(YELLOW if args.apply else GREEN, "MODE",
        f"{'GHI THẬT' if args.apply else 'CHẠY THỬ (không ghi gì)'} · chế độ {args.mode}")
    act_as(args.as_user)

    failed = False
    try:
        with transaction.atomic():
            for name, label in FILES:
                path = args.folder / name
                try:
                    headers, rows = read_table(path.read_bytes(), path.name)
                except DataFileError as exc:
                    say(RED, "LỖI", f"{name}: không đọc được ({exc})")
                    failed = True
                    break
                dataset = get_dataset(label)
                report = dataset.analyze(headers, rows, mode=args.mode)
                summary = (f"{name:<26} {len(rows):>4} dòng · mới {report.new_count} · "
                           f"cập nhật {report.update_count} · bỏ qua {report.skipped_count} · "
                           f"lỗi {report.error_count}")
                if report.fatal or report.missing_columns or report.error_count:
                    say(RED, "LỖI", summary)
                    if report.fatal:
                        say(RED, "    ", report.fatal)
                    if report.missing_columns:
                        say(RED, "    ", f"thiếu cột: {', '.join(report.missing_columns)}")
                    for r in report.problem_rows[:20]:
                        say(RED, "    ", f"dòng {r.number} {r.display}: {'; '.join(map(str, r.errors))}")
                    failed = True
                    break
                say(GREEN, "OK ", summary)
                if report.unknown_columns:
                    say(YELLOW, "    ", f"cột lạ bị bỏ qua: {', '.join(report.unknown_columns)}")
                if report.write_count:
                    dataset.apply(report)
            if failed or not args.apply:
                raise DryRun
    except DryRun:
        pass

    if failed:
        say(RED, "HUỶ", "Có lỗi -> đã rollback, KHÔNG ghi dòng nào. Sửa CSV rồi chạy lại.")
        sys.exit(1)
    if args.apply:
        say(GREEN, "XONG", "Đã ghi. Hậu kiểm: python manage.py check_keigo_data --settings=" + args.settings)
    else:
        print(f"\n{DIM}Đã rollback.{RESET} Chạy lại với {YELLOW}--apply{RESET} để ghi thật.")


if __name__ == "__main__":
    main()
