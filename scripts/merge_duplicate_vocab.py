"""
Gộp từ vựng trùng lặp trên Supabase: chuyển dữ liệu của từ bị xoá sang từ được
giữ, rồi mới xoá — không mất câu ví dụ, chủ đề, tiến độ học, phiếu luyện viết...

File kế hoạch (.csv) mỗi dòng 1 cặp, cột bắt buộc:
    keep_id, keep_word, keep_reading, delete_id, delete_word, delete_reading
    lay_nghia_tu_ban_xoa   (tuỳ chọn) 1 = ghi nghĩa của bản xoá sang bản giữ
Cột chữ/cách đọc dùng để chặn nhầm id: lệch với DB là dừng, không ghi gì.

    # 1. chạy thử — làm hết trong transaction rồi rollback, in số liệu thật
    python scripts/merge_duplicate_vocab.py "Claude outputs/vocab_trung_lap.csv"

    # 2. ghi thật
    python scripts/merge_duplicate_vocab.py "Claude outputs/vocab_trung_lap.csv" --apply --as-user dat

Với mỗi cặp (giữ K, xoá D), dữ liệu của D:
    - Câu ví dụ        → chuyển sang K, trừ câu K đã có (so theo câu tiếng Nhật).
    - Chủ đề           → thêm chủ đề K còn thiếu.
    - Tiến độ học      → người chỉ học D: chuyển sang K. Học cả hai: giữ bản ôn nhiều lần hơn.
    - Phiếu luyện viết, sổ từ, sổ câu sai → chuyển sang K, trừ chỗ đã có K.
    - Đóng góp/bình luận, báo lỗi, kính ngữ, câu trả lời bài kiểm tra → trỏ sang K.
    - K thiếu âm Hán Việt mà D có → lấy của D.
Toàn bộ trong MỘT transaction. Chạy lại sau khi đã xoá: các cặp đã xử lý được bỏ qua.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from _vocab_common import DIM, GREEN, RED, YELLOW, DryRun, act_as, norm, say, setup_django

REQUIRED = ("keep_id", "keep_word", "keep_reading", "delete_id", "delete_word", "delete_reading")


def read_plan(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            say(RED, "LỖI", f"File thiếu cột: {', '.join(missing)}")
            sys.exit(1)
        return [(n, row) for n, row in enumerate(reader, start=2)]


def main() -> None:
    ap = argparse.ArgumentParser(description="Gộp + xoá từ vựng trùng lặp theo file kế hoạch.")
    ap.add_argument("plan", type=Path, help="File .csv kế hoạch gộp.")
    ap.add_argument("--apply", action="store_true", help="Ghi thật. Không có cờ này thì chỉ chạy thử.")
    ap.add_argument("--as-user", metavar="USERNAME", help="Ghi created_by/updated_by là user này.")
    ap.add_argument("--settings", default="config.settings.supabase",
                    help="DJANGO_SETTINGS_MODULE (mặc định config.settings.supabase).")
    args = ap.parse_args()
    if not args.plan.exists():
        say(RED, "LỖI", f"Không thấy file {args.plan}")
        sys.exit(1)

    setup_django(args.settings)
    from django.db import transaction

    from apps.error_reports.models import ErrorReport
    from apps.exam.models import ExamAnswer, WrongBookEntry
    from apps.gamification.models import Contribution
    from apps.keigo.models import KeigoForm
    from apps.learning.models import UserVocabularyProgress, UserWordlistWord
    from apps.practice_sheets.models import PracticeSheetWord
    from apps.vocabulary.models import ExampleSentence, Vocabulary, VocabularyTopic

    # Bảng trỏ tới Vocabulary -> cột (ngoài khoá ngoại) quyết định "đã có ở K".
    # None = chỉ cần trỏ lại, không có ràng buộc trùng.
    MOVES = {
        PracticeSheetWord: ("sheet_id",),
        UserWordlistWord: ("wordlist_id",),
        WrongBookEntry: ("user_id", "question_type_code"),
        Contribution: None,
        ErrorReport: None,
        KeigoForm: None,
        ExamAnswer: None,
    }
    handled = set(MOVES) | {ExampleSentence, VocabularyTopic, UserVocabularyProgress}
    unknown = [rel.related_model for rel in Vocabulary._meta.related_objects
               if not rel.many_to_many and rel.related_model not in handled]
    if unknown:  # có bảng mới trỏ tới Vocabulary mà script chưa biết -> dừng, tránh xoá dây chuyền
        say(RED, "LỖI", "Script chưa xử lý bảng: " + ", ".join(m._meta.label for m in unknown))
        sys.exit(1)

    say(YELLOW if args.apply else GREEN, "MODE", "GHI THẬT" if args.apply else "CHẠY THỬ (không ghi gì)")
    act_as(args.as_user)

    plan = read_plan(args.plan)
    say(DIM, "FILE", f"{args.plan} — {len(plan)} cặp")
    ids = {int(r[c]) for _, r in plan for c in ("keep_id", "delete_id")}
    vocab = Vocabulary.objects.in_bulk(ids)
    keeps = {int(r["keep_id"]) for _, r in plan}

    pairs, problems, already = [], [], 0
    for n, r in plan:
        k_id, d_id = int(r["keep_id"]), int(r["delete_id"])
        k, d = vocab.get(k_id), vocab.get(d_id)
        if d is None:
            already += 1  # đã xoá ở lần chạy trước
            continue
        if k is None:
            problems.append(f"dòng {n}: không có từ giữ #{k_id}")
        elif d_id in keeps or k_id == d_id:
            problems.append(f"dòng {n}: #{d_id} vừa bị xoá vừa được giữ")
        elif (k.word, k.reading, d.word, d.reading) != (
                r["keep_word"], r["keep_reading"], r["delete_word"], r["delete_reading"]):
            problems.append(f"dòng {n}: chữ/cách đọc trong file lệch với DB (#{k_id} / #{d_id})")
        else:
            pairs.append((k, d, r.get("lay_nghia_tu_ban_xoa", "").strip() == "1"))
    if problems:
        for p in problems[:20]:
            say(RED, "LỖI", p)
        say(RED, "DỪNG", f"{len(problems)} dòng lỗi — không ghi gì.")
        sys.exit(1)
    if already:
        say(DIM, "BỎ QUA", f"{already} cặp đã xoá từ trước")

    stats = {k: 0 for k in ("ví dụ chuyển", "ví dụ trùng bỏ", "chủ đề thêm", "tiến độ chuyển",
                            "tiến độ trùng bỏ", "liên kết khác chuyển", "liên kết trùng bỏ", "từ xoá")}

    def merge(k, d, take_meaning):
        k_sentences = {norm(s) for s in k.examples.values_list("sentence_jp", flat=True)}
        for ex in d.examples.all():
            if norm(ex.sentence_jp) in k_sentences:
                stats["ví dụ trùng bỏ"] += 1
            else:
                ex.vocabulary = k
                ex.save(update_fields=["vocabulary", "updated_by", "updated_at"])
                k_sentences.add(norm(ex.sentence_jp))
                stats["ví dụ chuyển"] += 1

        k_topics = set(k.topic_links.values_list("topic_id", flat=True))
        for topic_id in d.topic_links.exclude(topic_id__in=k_topics).values_list("topic_id", flat=True):
            VocabularyTopic.objects.create(vocabulary=k, topic_id=topic_id)
            stats["chủ đề thêm"] += 1

        k_progress = {p.user_id: p for p in k.progress.all()}
        for p in d.progress.all():
            mine = k_progress.get(p.user_id)
            if mine is not None and mine.correct_count + mine.wrong_count >= p.correct_count + p.wrong_count:
                stats["tiến độ trùng bỏ"] += 1
                continue  # bản của K ôn nhiều hơn -> bản của D xoá theo D
            if mine is not None:
                mine.delete()
                stats["tiến độ trùng bỏ"] += 1
            p.vocabulary = k
            p.save(update_fields=["vocabulary", "updated_by", "updated_at"])
            stats["tiến độ chuyển"] += 1

        for model, unique in MOVES.items():
            fk = next(f.name for f in model._meta.fields if f.related_model is Vocabulary)
            rows = model.objects.filter(**{fk: d})
            if unique is None:
                stats["liên kết khác chuyển"] += rows.update(**{fk: k})
                continue
            taken = set(model.objects.filter(**{fk: k}).values_list(*unique))
            for row in rows:
                if tuple(getattr(row, c) for c in unique) in taken:
                    stats["liên kết trùng bỏ"] += 1  # K đã có -> xoá theo D
                else:
                    model.objects.filter(pk=row.pk).update(**{fk: k})
                    stats["liên kết khác chuyển"] += 1

        changed = []
        if take_meaning and d.meaning_vi and k.meaning_vi != d.meaning_vi:
            k.meaning_vi = d.meaning_vi
            changed.append("meaning_vi")
        if not k.han_viet and d.han_viet:
            k.han_viet = d.han_viet
            changed.append("han_viet")
        d.delete()
        stats["từ xoá"] += 1
        if changed:
            k.save(update_fields=changed + ["updated_by", "updated_at"])

    try:
        with transaction.atomic():
            for k, d, take_meaning in pairs:
                say(DIM, "GỘP", f"#{d.pk} {d.word}【{d.reading}】 → #{k.pk} {k.word}【{k.reading}】")
                merge(k, d, take_meaning)
            if not args.apply:
                raise DryRun
    except DryRun:
        pass

    say(DIM, "TỔNG", " · ".join(f"{v} {k}" for k, v in stats.items()))
    if args.apply:
        say(GREEN, "XONG", f"Đã gộp và xoá {stats['từ xoá']} từ.")
    else:
        say(GREEN, "XONG", "Chạy thử xong (đã rollback). Thêm --apply để ghi thật.")


if __name__ == "__main__":
    main()
