"""
Đẩy từ vựng mới từ file CSV / Excel lên Supabase.

File đầu vào dùng ĐÚNG mẫu "từ vựng đầy đủ" của màn nhập dữ liệu SC07b (tải mẫu
ở Quản trị > Dữ liệu), nên một file soạn sẵn dùng được cho cả hai đường:

    word*, reading*, meaning_vi*, audio_url, topics,
    example1_jp, example1_vi, example2_jp, example2_vi, example3_jp, example3_vi
    (* = bắt buộc; topics = các slug ngăn bằng dấu ; — vd "meeting;keigo")

    # 1. chạy thử — kiểm tra file + so với DB, KHÔNG ghi gì (mặc định)
    python scripts/upload_vocab.py tu_moi.xlsx

    # 2. ghi thật, người tạo là tài khoản dat
    python scripts/upload_vocab.py tu_moi.xlsx --apply --as-user dat

    # gắn thêm 1 topic cho MỌI dòng (vd cả file là bài 46)
    python scripts/upload_vocab.py bai46.csv --topic lesson46 --apply --as-user dat

Với mỗi dòng:
    - Kiểm tra: đủ cột bắt buộc, độ dài khớp model, slug topic có trên DB,
      không trùng với dòng khác trong file, xác định được hàng kana.
    - Từ CHƯA có (so theo chữ + cách đọc, bỏ qua （する）/ katakana-hiragana
      như dữ liệu hiện tại): tạo Vocabulary, gắn topic trong cột topics +
      --topic + topic hàng kana (あ行, か行...) tự tính từ cách đọc, thêm câu ví dụ.
    - Từ ĐÃ có: không tạo trùng; chỉ THÊM topic và câu ví dụ còn thiếu.
      --update-meaning thì ghi đè nghĩa bằng nghĩa trong file.
    - Cùng chữ nhưng khác cách đọc (vd 目下 めした/もっか): coi là từ khác,
      vẫn tạo mới nhưng in cảnh báo để soát — trên DB có nhiều cách đọc bị
      sinh tự động sai.

Có dòng lỗi thì KHÔNG ghi gì (trừ khi thêm --skip-invalid để bỏ qua các dòng
lỗi). Toàn bộ chạy trong MỘT transaction; chạy lại cùng file ra cùng kết quả.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

from _vocab_common import (
    DIM, GREEN, RED, RESET, YELLOW, DryRun, act_as, kana_line_slug, norm, rkey,
    say, setup_django, wkey,
)

EXAMPLE_SLOTS = 3
REQUIRED = ("word", "reading", "meaning_vi")


def read_rows(path: Path):
    """[(số dòng trong file, {cột: giá trị})] — dùng chung bộ đọc với SC07b."""
    from apps.core.dataio import DataFileError, read_table

    try:
        headers, rows = read_table(path.read_bytes(), path.name)
    except DataFileError as exc:
        say(RED, "LỖI", f"Không đọc được {path.name}: {exc}")
        sys.exit(1)
    missing = [h for h in REQUIRED if h not in headers]
    if missing:
        say(RED, "LỖI", f"File thiếu cột: {', '.join(missing)}. Có: {', '.join(headers)}")
        sys.exit(1)
    out = []
    for i, row in enumerate(rows, start=2):  # dòng 1 là tiêu đề
        data = {h: str(row[j]).strip() if j < len(row) and row[j] is not None else ""
                for j, h in enumerate(headers) if h}
        if any(data.values()):
            out.append((i, data))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Đẩy từ vựng mới từ CSV/Excel lên Supabase.")
    ap.add_argument("file", type=Path, help="File .csv / .xlsx theo mẫu 'từ vựng đầy đủ' của SC07b.")
    ap.add_argument("--apply", action="store_true", help="Ghi thật. Không có cờ này thì chỉ chạy thử.")
    ap.add_argument("--topic", action="append", default=[], metavar="SLUG",
                    help="Gắn thêm topic này cho mọi dòng (dùng nhiều lần được).")
    ap.add_argument("--update-meaning", action="store_true",
                    help="Từ đã có: ghi đè nghĩa bằng nghĩa trong file.")
    ap.add_argument("--skip-invalid", action="store_true",
                    help="Bỏ qua dòng lỗi và vẫn ghi các dòng hợp lệ.")
    ap.add_argument("--as-user", metavar="USERNAME",
                    help="Ghi created_by/updated_by là user này (mặc định để trống = hệ thống).")
    ap.add_argument("--settings", default="config.settings.supabase",
                    help="DJANGO_SETTINGS_MODULE (mặc định config.settings.supabase).")
    ap.add_argument("--report", metavar="CSV", help="Ghi kết quả từng dòng ra file CSV.")
    args = ap.parse_args()

    if not args.file.exists():
        say(RED, "LỖI", f"Không thấy file {args.file}")
        sys.exit(1)

    setup_django(args.settings)
    from django.db import transaction

    from apps.core import middleware
    from apps.vocabulary.models import ExampleSentence, Topic, Vocabulary, VocabularyTopic

    say(YELLOW if args.apply else GREEN, "MODE", "GHI THẬT" if args.apply else "CHẠY THỬ (không ghi gì)")
    act_as(args.as_user)

    rows = read_rows(args.file)
    say(DIM, "FILE", f"{args.file} — {len(rows)} dòng")

    max_len = {f: Vocabulary._meta.get_field(f).max_length for f in ("word", "reading", "meaning_vi")}
    max_example = ExampleSentence._meta.get_field("sentence_jp").max_length
    topics = {t.slug: t for t in Topic.objects.all()}
    for slug in args.topic:
        if slug not in topics:
            say(RED, "LỖI", f"--topic {slug}: không có topic này trên DB.")
            sys.exit(1)

    by_pair, by_word = {}, defaultdict(list)
    for v in Vocabulary.objects.all():
        by_pair[(wkey(v.word), rkey(v.reading))] = v
        by_word[wkey(v.word)].append(v)

    # --- 1. Kiểm tra từng dòng -------------------------------------------------
    plans, errors, seen = [], 0, {}
    for line, data in rows:
        problems = [f"thiếu {h}" for h in REQUIRED if not data.get(h)]
        problems += [f"{h} dài quá {n} ký tự" for h, n in max_len.items() if len(data.get(h, "")) > n]
        slugs = list(dict.fromkeys(
            [s.strip() for s in data.get("topics", "").replace(",", ";").split(";") if s.strip()] + args.topic
        ))
        problems += [f"không có topic '{s}'" for s in slugs if s not in topics]
        examples = []
        for i in range(1, EXAMPLE_SLOTS + 1):
            jp, vi = data.get(f"example{i}_jp", ""), data.get(f"example{i}_vi", "")
            if jp or vi:
                if not (jp and vi):
                    problems.append(f"example{i}: phải điền cả _jp lẫn _vi")
                elif max(len(jp), len(vi)) > max_example:
                    problems.append(f"example{i} dài quá {max_example} ký tự")
                else:
                    examples.append((jp, vi))
        key = (wkey(data.get("word")), rkey(data.get("reading")))
        if key in seen:
            problems.append(f"trùng dòng {seen[key]} trong file")
        seen.setdefault(key, line)
        line_slug = kana_line_slug(data.get("reading"))
        if data.get("reading") and line_slug not in topics:
            problems.append(f"không xác định được hàng kana từ '{data['reading']}'")
        if problems:
            errors += 1
        plans.append(dict(line=line, data=data, slugs=slugs, examples=examples,
                          line_slug=line_slug, key=key, problems=problems))

    for p in plans:
        if p["problems"]:
            say(RED, f"  dòng {p['line']:>4}", f"{p['data'].get('word', '')}: {'; '.join(p['problems'])}")
    if errors and not args.skip_invalid:
        say(RED, "\nDỪNG", f"{errors} dòng lỗi — sửa file rồi chạy lại, hoặc thêm --skip-invalid.")
        sys.exit(1)

    # --- 2. Ghi ----------------------------------------------------------------
    stats, report = Counter(), []
    links = set(VocabularyTopic.objects.values_list("vocabulary_id", "topic_id"))
    line_topic_ids = {t.pk for slug, t in topics.items() if slug.endswith("-line")}

    def link(vocab, topic):
        if (vocab.pk, topic.pk) in links:
            return 0
        VocabularyTopic.objects.create(vocabulary=vocab, topic=topic)
        links.add((vocab.pk, topic.pk))
        return 1

    try:
        with transaction.atomic():
            for p in plans:
                data, notes = p["data"], []
                if p["problems"]:
                    stats["bỏ qua (lỗi)"] += 1
                    report.append([p["line"], data.get("word"), data.get("reading"), "bỏ qua (lỗi)", "",
                                   0, 0, "; ".join(p["problems"])])
                    continue

                vocab = by_pair.get(p["key"])
                if vocab is None:
                    vocab = Vocabulary(word=data["word"], reading=data["reading"],
                                       meaning_vi=data["meaning_vi"], audio_url=data.get("audio_url", ""))
                    vocab.save()
                    others = [v for v in by_word.get(p["key"][0], []) if v.pk != vocab.pk]
                    if others:
                        notes.append("cùng chữ khác cách đọc với " + ", ".join(
                            f"#{v.pk} {v.reading}" for v in others) + " — kiểm tra lại cách đọc")
                    by_pair[p["key"]] = vocab
                    by_word[p["key"][0]].append(vocab)
                    action = "tạo mới"
                else:
                    action = "đã có"
                    if norm(vocab.meaning_vi) != norm(data["meaning_vi"]):
                        if args.update_meaning:
                            notes.append(f"nghĩa: {vocab.meaning_vi} → {data['meaning_vi']}")
                            vocab.meaning_vi = data["meaning_vi"]
                            vocab.save()
                            stats["cập nhật nghĩa"] += 1
                        else:
                            notes.append(f"nghĩa trên DB khác: {vocab.meaning_vi}")

                added = sum(link(vocab, topics[s]) for s in p["slugs"])
                # Từ mới luôn có topic hàng kana; từ cũ thì chỉ bổ sung nếu còn thiếu.
                if not any((vocab.pk, tid) in links for tid in line_topic_ids):
                    added += link(vocab, topics[p["line_slug"]])

                existing = {norm(e) for e in vocab.examples.values_list("sentence_jp", flat=True)}
                new_examples = 0
                for jp, vi in p["examples"]:
                    if norm(jp) not in existing:
                        ExampleSentence(vocabulary=vocab, sentence_jp=jp, sentence_vi=vi).save()
                        existing.add(norm(jp))
                        new_examples += 1

                stats[action] += 1
                stats["liên kết topic"] += added
                stats["câu ví dụ"] += new_examples
                report.append([p["line"], vocab.word, vocab.reading, action, vocab.pk,
                               added, new_examples, " · ".join(notes)])
                color = GREEN if action == "tạo mới" else DIM
                say(YELLOW if notes else color, f"  {action:>8}",
                    f"{vocab.word} ({vocab.reading}) +{added} topic +{new_examples} ví dụ"
                    + (f"  [{' · '.join(notes)}]" if notes else ""))

            if not args.apply:
                raise DryRun
    except DryRun:
        say(GREEN, "\nROLLBACK", "Chạy thử xong — đã huỷ mọi thay đổi.")
    finally:
        middleware._thread_locals.user = None

    print()
    for key in ("tạo mới", "đã có", "bỏ qua (lỗi)", "cập nhật nghĩa", "liên kết topic", "câu ví dụ"):
        if stats[key] or key in ("tạo mới", "đã có"):
            print(f"  {key:<16}: {stats[key]}")

    if args.report:
        with open(args.report, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["line", "word", "reading", "action", "vocabulary_id", "topics_added",
                        "examples_added", "note"])
            w.writerows(report)
        say(DIM, "REPORT", args.report)
    if not args.apply:
        print(f"\nChạy lại với {YELLOW}--apply{RESET} để ghi thật.")


if __name__ == "__main__":
    main()
