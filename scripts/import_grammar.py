"""
Đẩy 500 mẫu ngữ pháp (docs/data/grammar/grammar_pattern.csv) lên Supabase.

    # 1. chạy thử — kiểm file + so với DB, KHÔNG ghi gì (mặc định)
    python scripts/import_grammar.py

    # 2. ghi thật, người tạo là tài khoản dat
    python scripts/import_grammar.py --apply --as-user dat

CSV xuất một lần từ bảng grammar_pattern của bjt.db (BJT-WEB). Logic ở apps/grammar/importer.py:
idempotent theo pattern. Một transaction; lỗi ở đâu rollback hết.
"""
import argparse
import sys

from _vocab_common import BASE_DIR, DIM, GREEN, RED, RESET, YELLOW, DryRun, act_as, say, setup_django

DEFAULT_CSV = BASE_DIR / "docs" / "data" / "grammar" / "grammar_pattern.csv"


def main():
    ap = argparse.ArgumentParser(description="Nhập mẫu ngữ pháp lên Supabase.")
    ap.add_argument("--csv", default=str(DEFAULT_CSV), help="File CSV (mặc định docs/data/grammar/grammar_pattern.csv).")
    ap.add_argument("--apply", action="store_true", help="Ghi thật. Không có cờ này thì chỉ chạy thử.")
    ap.add_argument("--as-user", metavar="USERNAME", help="Ghi created_by/updated_by là user này.")
    ap.add_argument("--settings", default="config.settings.supabase", help="DJANGO_SETTINGS_MODULE.")
    args = ap.parse_args()

    setup_django(args.settings)
    from django.db import transaction

    from apps.core import middleware
    from apps.grammar import importer

    say(YELLOW if args.apply else GREEN, "MODE", "GHI THẬT" if args.apply else "CHẠY THỬ (không ghi gì)")
    rows = importer.read_rows(args.csv)
    say(DIM, "FILE", f"{args.csv} — {len(rows)} mẫu")

    errors = importer.validate(rows)
    if errors:
        for line, msg in errors:
            say(RED, f"  dòng {line:>4}", msg)
        say(RED, "DỪNG", f"{len(errors)} lỗi trong file — sửa rồi chạy lại.")
        sys.exit(1)

    act_as(args.as_user)
    try:
        with transaction.atomic():
            new, updated, same = importer.apply_rows(rows)
            if not args.apply:
                raise DryRun
    except DryRun:
        say(GREEN, "ROLLBACK", "Chạy thử xong — đã huỷ mọi thay đổi.")
    finally:
        middleware._thread_locals.user = None

    print(f"\n  Tạo mới    : {new}\n  Cập nhật   : {updated}\n  Giữ nguyên : {same}")
    if not args.apply:
        print(f"\nChạy lại với {YELLOW}--apply{RESET} để ghi thật.")


if __name__ == "__main__":
    main()
