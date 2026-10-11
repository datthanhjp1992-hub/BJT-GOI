"""
Đẩy 500 câu đề thi thử (docs/data/exam/exam_question.csv) lên Supabase — docs/SPEC_KIEM_TRA.md T7.2.

    # 1. chạy thử — kiểm file + so với DB, KHÔNG ghi gì (mặc định)
    python scripts/import_exam.py

    # 2. ghi thật, người tạo là tài khoản dat
    python scripts/import_exam.py --apply --as-user dat

CSV sinh từ bjt.db bằng scripts/export_bjt_exam.py. Logic ở apps/exam/importer.py:
idempotent theo source_ref, câu đã có thì cập nhật nội dung nhưng GIỮ is_active và
audio_version. Một transaction; lỗi ở đâu rollback hết. Sau khi ghi tự chạy soát dữ liệu
(như `manage.py check_exam_data`).
"""
import argparse
import sys

from _vocab_common import BASE_DIR, DIM, GREEN, RED, RESET, YELLOW, DryRun, act_as, say, setup_django

DEFAULT_CSV = BASE_DIR / "docs" / "data" / "exam" / "exam_question.csv"


def main():
    ap = argparse.ArgumentParser(description="Nhập đề thi thử lên Supabase.")
    ap.add_argument("--csv", default=str(DEFAULT_CSV), help="File CSV (mặc định docs/data/exam/exam_question.csv).")
    ap.add_argument("--apply", action="store_true", help="Ghi thật. Không có cờ này thì chỉ chạy thử.")
    ap.add_argument("--as-user", metavar="USERNAME", help="Ghi created_by/updated_by là user này.")
    ap.add_argument("--settings", default="config.settings.supabase", help="DJANGO_SETTINGS_MODULE.")
    args = ap.parse_args()

    setup_django(args.settings)
    from django.db import transaction

    from apps.core import middleware
    from apps.exam import importer

    say(YELLOW if args.apply else GREEN, "MODE", "GHI THẬT" if args.apply else "CHẠY THỬ (không ghi gì)")
    rows = importer.read_rows(args.csv)
    say(DIM, "FILE", f"{args.csv} — {len(rows)} câu")

    errors = importer.validate(rows)
    if errors:
        for line, msg in errors:
            say(RED, f"  dòng {line:>4}" if line else "  ", msg)
        say(RED, "DỪNG", f"{len(errors)} lỗi trong file — sửa rồi chạy lại.")
        sys.exit(1)

    act_as(args.as_user)
    problems = []
    try:
        with transaction.atomic():
            stats = importer.apply_rows(rows)
            problems = importer.check_database()
            if not args.apply:
                raise DryRun
    except DryRun:
        say(GREEN, "ROLLBACK", "Chạy thử xong — đã huỷ mọi thay đổi.")
    finally:
        middleware._thread_locals.user = None

    print()
    print(f"  Bộ đề tạo mới : {stats.sets_new}")
    print(f"  Câu tạo mới   : {stats.new}")
    print(f"  Câu cập nhật  : {stats.updated}")
    print(f"  Giữ nguyên    : {stats.same}")
    if problems:
        print(f"\n{RED}Soát dữ liệu sau khi nhập: {len(problems)} lỗi{RESET}")
        for p in problems:
            print("   •", p)
    else:
        print(f"\n{GREEN}Soát dữ liệu sau khi nhập: ổn.{RESET}")
    if not args.apply:
        print(f"\nChạy lại với {YELLOW}--apply{RESET} để ghi thật.")


if __name__ == "__main__":
    main()
