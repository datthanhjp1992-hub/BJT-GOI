"""
Tạo audio cho các đoạn bản tin (NewsSegment) bằng VOICEVOX — docs/SPEC_NGHE_BAN_TIN.md mục 4.

    # tạo mp3 vào media/news_audio/n<segment_id>.mp3 (chạy lại thì bỏ qua đoạn không đổi)
    python scripts/generate_news_audio.py

    # rồi upload + ghi NewsSegment.audio_url
    python scripts/upload_vocab_audio.py media/news_audio --apply --as-user dat

Dùng chung giọng + cách mã hoá với scripts/generate_vocab_audio.py (No.7 アナウンス, mp3 48 kbps).
Chỉ ĐỌC database. Cần VOICEVOX đang chạy ở 127.0.0.1:50021 và lameenc.
Credit bắt buộc khi dùng audio: 「VOICEVOX:No.7」.
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from _vocab_common import BASE_DIR, DIM, GREEN, RED, say, setup_django
from generate_vocab_audio import ENGINE, SPEAKER, _post, audio_query, to_mp3


def main():
    ap = argparse.ArgumentParser(description="Tạo audio VOICEVOX cho đoạn bản tin.")
    ap.add_argument("--out", type=Path, default=BASE_DIR / "media" / "news_audio")
    ap.add_argument("--limit", type=int, help="Chỉ xử lý N đoạn đầu (thử nhanh).")
    ap.add_argument("--settings", default="config.settings.supabase", help="DJANGO_SETTINGS_MODULE.")
    args = ap.parse_args()

    try:
        say(DIM, "ENGINE", f"VOICEVOX {urllib.request.urlopen(ENGINE + '/version', timeout=5).read().decode()}")
    except OSError:
        say(RED, "LỖI", f"Không gọi được VOICEVOX ở {ENGINE} — mở VOICEVOX rồi chạy lại.")
        sys.exit(1)

    setup_django(args.settings)
    from apps.news.models import NewsSegment
    from apps.vocabulary.audio import speak_text

    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    segments = NewsSegment.objects.order_by("lesson__number", "number")
    if args.limit:
        segments = segments[: args.limit]
    made = skipped = 0
    try:
        for seg in segments:
            name, text = f"n{seg.id}.mp3", speak_text(seg.text_jp)
            digest = hashlib.sha1(f"{SPEAKER}|{text}".encode()).hexdigest()
            if manifest.get(name) == digest and (args.out / name).exists():
                skipped += 1
                continue
            (args.out / name).write_bytes(to_mp3(_post("/synthesis", {"speaker": SPEAKER}, audio_query(text))))
            manifest[name] = digest
            made += 1
            say(DIM, "…", f"{name} ({seg.lesson_id}-{seg.number})")
    finally:  # Ctrl+C giữa chừng vẫn giữ manifest
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    say(GREEN, "XONG", f"tạo {made} file, bỏ qua {skipped} file không đổi → {args.out}")


if __name__ == "__main__":
    main()
