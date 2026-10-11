"""
Đưa 23 chủ đề nghiệp vụ + phân loại từ vựng BJT (từ bjt.db của BJT-WEB) lên Supabase.

Dữ liệu đầu vào nằm trong repo, không đọc bjt.db:
    docs/data/vocab_bjt/topics.csv        23 topic, cùng kiểu với topic đang có
                                         (slug + name tiếng Anh, name_ja, mô tả tiếng Việt)
    docs/data/vocab_bjt/vocab_topics.csv  1.018 từ đã gộp trùng, mỗi từ 1 slug chủ đề

    # 1. chạy thử — in báo cáo, KHÔNG ghi gì (mặc định)
    python scripts/import_bjt_topics.py --report bao_cao.csv

    # 2. ghi thật, ghi người tạo là tài khoản dat
    python scripts/import_bjt_topics.py --apply --as-user dat

    # 2b. ghi thật + sửa luôn chữ/cách đọc/nghĩa sai của các từ ĐÃ CÓ trên DB
    python scripts/import_bjt_topics.py --apply --as-user dat --fix-existing

Script làm gì, theo đúng cấu trúc topic đang có trên DB:
    1. Tạo/cập nhật 23 topic (khoá: slug). Không đụng tới topic cũ (あ行..., LessonN).
    2. Với mỗi từ trong CSV, tìm từ đã có trên DB theo thứ tự:
         khớp đúng    (word, reading) đã sửa
         khớp bản gốc (word, reading) gốc trong bjt.db
         khớp theo chữ chỉ theo word
         khớp một phần một trong các dạng thay thế 'A、B' / 'A・B' / 'A=B'
       So khớp bỏ qua các quy ước của lần nhập trước: hậu tố （する）, dấu "..."
       ở đầu, katakana/hiragana trong cách đọc.
       - Tìm thấy: THÊM liên kết tới topic nghiệp vụ. Không gỡ liên kết nào.
       - Không thấy: tạo Vocabulary mới + liên kết topic nghiệp vụ + topic hàng
         kana (あ行, か行...) theo chữ đầu của cách đọc. Chữ có dấu quy về hàng gốc
         (が→か行, ぱ→は行), katakana quy về hiragana — đúng như dữ liệu hiện tại.
    3. --fix-existing (không áp cho "khớp một phần"):
       - chữ/cách đọc khác bản đã sửa thì sửa lại, giữ hậu tố （する） nếu DB đang
         dùng; bỏ qua nếu sửa xong đụng unique (word, reading) — báo để xử lý tay;
         đổi cách đọc thì đổi luôn topic hàng kana.
       - nghĩa chỉ ghi đè khi nghĩa trên DB vẫn y nguyên nghĩa gốc của bjt.db,
         tức là chưa ai sửa tay.

Toàn bộ chạy trong MỘT transaction; lỗi ở đâu là rollback hết. Chạy lại nhiều
lần ra cùng kết quả (idempotent).
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict

from _vocab_common import (
    BASE_DIR, DIM, GREEN, RED, RESET, SURU, YELLOW, DryRun, act_as, alt_parts,
    kana_line_slug, norm, rkey, say, setup_django, to_hiragana, wkey,
)

DATA_DIR = BASE_DIR / "docs" / "data" / "vocab_bjt"


def read_csv(name):
    with open(DATA_DIR / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def split_multi(value):
    return [v.strip() for v in (value or "").split("¦") if v.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description="Đưa topic nghiệp vụ + phân loại từ vựng BJT lên Supabase.")
    ap.add_argument("--apply", action="store_true", help="Ghi thật. Không có cờ này thì chỉ chạy thử.")
    ap.add_argument("--fix-existing", action="store_true",
                    help="Sửa chữ/cách đọc/nghĩa sai của các từ đã có trên DB.")
    ap.add_argument("--as-user", metavar="USERNAME",
                    help="Ghi created_by/updated_by là user này (mặc định để trống = hệ thống).")
    ap.add_argument("--settings", default="config.settings.supabase",
                    help="DJANGO_SETTINGS_MODULE (mặc định config.settings.supabase).")
    ap.add_argument("--report", metavar="CSV", help="Ghi chi tiết từng từ ra file CSV.")
    ap.add_argument("--verbose", action="store_true", help="In chi tiết từng từ.")
    args = ap.parse_args()

    setup_django(args.settings)
    from django.db import transaction

    from apps.core import middleware
    from apps.vocabulary.models import Topic, Vocabulary, VocabularyTopic

    say(YELLOW if args.apply else GREEN, "MODE",
        ("GHI THẬT" if args.apply else "CHẠY THỬ (không ghi gì)")
        + (" + sửa từ đã có" if args.fix_existing else ""))
    act_as(args.as_user)

    topic_rows = read_csv("topics.csv")
    vocab_rows = read_csv("vocab_topics.csv")
    stats = Counter()
    report = []

    try:
        with transaction.atomic():
            # --- 1. Topic -----------------------------------------------------
            topics = {}
            for row in topic_rows:
                topic = Topic.objects.filter(slug=row["slug"]).first()
                fields = {k: row[k] for k in ("name", "name_ja", "icon_emoji", "description")}
                if topic is None:
                    topic = Topic(slug=row["slug"], **fields)
                    topic.save()
                    stats["topic_new"] += 1
                elif any(getattr(topic, k) != v for k, v in fields.items()):
                    for k, v in fields.items():
                        setattr(topic, k, v)
                    topic.save()
                    stats["topic_updated"] += 1
                else:
                    stats["topic_same"] += 1
                topics[row["slug"]] = topic
            line_topics = {t.slug: t for t in Topic.objects.filter(slug__endswith="-line")}

            # --- 2. Chỉ mục từ đã có -------------------------------------------
            by_pair, by_word, by_part = {}, defaultdict(list), defaultdict(list)
            for v in Vocabulary.objects.all():
                by_pair[(wkey(v.word), rkey(v.reading))] = v
                by_word[wkey(v.word)].append(v)
                for k in alt_parts(v.word):
                    by_part[k].append(v)
            links = set(VocabularyTopic.objects.values_list("vocabulary_id", "topic_id"))

            def link(vocab, topic):
                if (vocab.pk, topic.pk) in links:
                    return False
                VocabularyTopic.objects.create(vocabulary=vocab, topic=topic)
                links.add((vocab.pk, topic.pk))
                return True

            def set_line_topic(vocab):
                slug = kana_line_slug(vocab.reading)
                if slug not in line_topics:
                    return f"không xác định được hàng kana từ '{vocab.reading}'"
                stale = VocabularyTopic.objects.filter(
                    vocabulary=vocab, topic__slug__endswith="-line"
                ).exclude(topic__slug=slug)
                for vt in stale:
                    links.discard((vocab.pk, vt.topic_id))
                stale.delete()
                link(vocab, line_topics[slug])
                return None

            def find(word, reading, orig_words, orig_readings):
                candidates = orig_words + [word]
                hit = by_pair.get((wkey(word), rkey(reading)))
                if hit:
                    return [hit], "khớp đúng"
                pairs = {(wkey(w), rkey(r)) for w in candidates for r in orig_readings + [reading]}
                found = [by_pair[p] for p in pairs if p in by_pair]
                if found:
                    return found, "khớp bản gốc"
                found = [v for k in {wkey(w) for w in candidates} for v in by_word.get(k, [])]
                if found:
                    return found, "khớp theo chữ"
                keys = set().union(*(alt_parts(w) for w in candidates)) | {wkey(w) for w in candidates}
                found = [v for k in keys for v in by_word.get(k, []) + by_part.get(k, [])]
                return found, "khớp một phần"

            def fix(v, word, reading, meaning, orig_meanings, how, notes):
                changed, reading_changed = [], False
                # Khớp một phần (DB chỉ giữ 1 dạng) thì không đổi chữ/cách đọc.
                if how != "khớp một phần":
                    suffix = "（する）" if SURU.search(norm(v.word)) else ""
                    new_word = word + suffix if wkey(v.word) != wkey(word) else v.word
                    new_reading = reading + suffix if rkey(v.reading) != rkey(reading) else v.reading
                    if new_reading != v.reading and v.reading == to_hiragana(v.reading):
                        # DB ghi cách đọc bằng hiragana (アプーチ/あぷーち) thì giữ kiểu đó.
                        new_reading = to_hiragana(new_reading)
                    if (new_word, new_reading) != (v.word, v.reading):
                        clash = by_pair.get((wkey(new_word), rkey(new_reading)))
                        if clash and clash.pk != v.pk:
                            notes.append(f"không sửa #{v.pk} {v.word}/{v.reading}: đụng #{clash.pk}")
                            stats["fix_clash"] += 1
                        else:
                            by_pair.pop((wkey(v.word), rkey(v.reading)), None)
                            reading_changed = rkey(v.reading) != rkey(new_reading)
                            changed.append(f"#{v.pk} {v.word}/{v.reading} → {new_word}/{new_reading}")
                            v.word, v.reading = new_word, new_reading
                            by_pair[(wkey(new_word), rkey(new_reading))] = v
                if norm(v.meaning_vi) != norm(meaning) and norm(v.meaning_vi) in orig_meanings:
                    changed.append(f"nghĩa: {v.meaning_vi} → {meaning}")
                    v.meaning_vi = meaning
                if changed:
                    v.save()
                    if reading_changed:
                        problem = set_line_topic(v)
                        if problem:
                            notes.append(problem)
                    stats["vocab_fixed"] += 1
                    notes.extend(changed)

            # --- 3. Từ vựng ---------------------------------------------------
            for row in vocab_rows:
                word, reading, meaning = row["word"], row["reading"], row["meaning_vi"]
                slugs = [s for s in row["topics"].split(";") if s]
                orig_words = split_multi(row["orig_words"]) or [word]
                orig_readings = split_multi(row["orig_readings"]) or [reading]
                orig_meanings = {norm(m) for m in split_multi(row["orig_meanings"])}
                notes = []

                matches, how = find(word, reading, orig_words, orig_readings)
                matches = list({v.pk: v for v in matches}.values())

                if not matches:
                    vocab = Vocabulary(word=word, reading=reading, meaning_vi=meaning)
                    vocab.save()
                    by_pair[(wkey(word), rkey(reading))] = vocab
                    by_word[wkey(word)].append(vocab)
                    problem = set_line_topic(vocab)
                    if problem:
                        notes.append(problem)
                        stats["no_line"] += 1
                    how = "tạo mới"
                    matches = [vocab]
                else:
                    if len(matches) > 1:
                        notes.append(f"{len(matches)} dòng trên DB cùng chữ — gắn topic cho tất cả, nên gộp tay")
                        stats["vocab_dup_on_db"] += 1
                    if how == "khớp một phần":
                        notes.append("DB: " + ", ".join(f"#{v.pk} {v.word}/{v.reading}" for v in matches))
                    if args.fix_existing:
                        for v in matches:
                            fix(v, word, reading, meaning, orig_meanings, how, notes)
                stats[how] += 1

                added = 0
                for v in matches:
                    for slug in slugs:
                        added += link(v, topics[slug])
                stats["links_added"] += added
                report.append([word, reading, ";".join(slugs), how, ",".join(str(v.pk) for v in matches),
                               added, " · ".join(notes)])
                if args.verbose or notes:
                    say(YELLOW if notes else DIM, f"  {how:>13}", f"{word} ({reading}) → {';'.join(slugs)}"
                        + (f"  [{' · '.join(notes)}]" if notes else ""))

            if not args.apply:
                raise DryRun
    except DryRun:
        say(GREEN, "\nROLLBACK", "Chạy thử xong — đã huỷ mọi thay đổi.")
    finally:
        middleware._thread_locals.user = None

    print()
    print(f"  Topic: tạo mới {stats['topic_new']}, cập nhật {stats['topic_updated']}, giữ nguyên {stats['topic_same']}")
    print(f"  Từ vựng ({len(vocab_rows)} dòng CSV):")
    for how in ("khớp đúng", "khớp bản gốc", "khớp theo chữ", "khớp một phần", "tạo mới"):
        print(f"    {how:<26}: {stats[how]}")
    print(f"    {'nhiều dòng DB cùng chữ':<26}: {stats['vocab_dup_on_db']}")
    if args.fix_existing:
        print(f"    {'đã sửa / đụng unique':<26}: {stats['vocab_fixed']} / {stats['fix_clash']}")
    if stats["no_line"]:
        print(f"    {RED}{'không gán được hàng kana':<26}: {stats['no_line']}{RESET}")
    print(f"  Liên kết topic thêm mới: {stats['links_added']}")

    if args.report:
        with open(args.report, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["word", "reading", "topics", "action", "vocabulary_ids", "links_added", "note"])
            w.writerows(report)
        say(DIM, "REPORT", args.report)
    if not args.apply:
        print(f"\nChạy lại với {YELLOW}--apply{RESET} để ghi thật.")


if __name__ == "__main__":
    main()
