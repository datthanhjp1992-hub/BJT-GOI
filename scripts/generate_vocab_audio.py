"""
Tạo audio từ vựng + câu ví dụ bằng VOICEVOX Engine chạy trên máy (giọng No.7 アナウンス).

    # 1. kiểm tra — chỉ hỏi engine cách đọc, KHÔNG tạo file (mặc định, ~vài phút)
    python scripts/generate_vocab_audio.py

    # 2. tạo mp3 vào media/vocab_audio/ (~1 giây/file; chạy lại thì bỏ qua file đã có)
    python scripts/generate_vocab_audio.py --generate

Cả hai đều ghi <out>/audio_report.csv để soát:
  - reading_mismatch : engine đọc chữ Hán khác Vocabulary.reading -> khi tạo sẽ đọc từ kana.
                       Thường là reading trên DB sai, hoặc từ nhiều cách đọc — nên nghe lại.
  - dirty_example    : câu lẫn tiếng Việt / số thừa cuối câu -> KHÔNG tạo audio, sửa dữ liệu trước.
Chỉ ĐỌC database; upload + ghi audio_url là bước riêng.

Cần: VOICEVOX đang mở (hoặc vv-engine/run.exe), API ở 127.0.0.1:50021.
--generate cần thêm: .venv\\Scripts\\pip install lameenc  (chỉ máy tạo audio, không vào requirements)
Credit bắt buộc khi dùng audio: 「VOICEVOX:No.7」.
"""
import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.parse
import urllib.request
import wave
from pathlib import Path

from _vocab_common import BASE_DIR, DIM, GREEN, RED, YELLOW, say, setup_django

ENGINE = "http://127.0.0.1:50021"
SPEAKER = 30          # No.7 アナウンス — Dat chọn sau pilot 17/10/2026
MP3_KBPS = 48         # giọng nói mono 24 kHz: 48 kbps đủ rõ, ~6 KB/giây


def _post(path, params, body=None):
    url = f"{ENGINE}{path}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def audio_query(text):
    q = json.loads(_post("/audio_query", {"text": text, "speaker": SPEAKER}))
    q["prePhonemeLength"] = q["postPhonemeLength"] = 0.15
    return q


def to_mp3(wav_bytes):
    import lameenc

    with wave.open(io.BytesIO(wav_bytes)) as w:
        enc = lameenc.Encoder()
        enc.set_bit_rate(MP3_KBPS)
        enc.set_in_sample_rate(w.getframerate())
        enc.set_channels(w.getnchannels())
        enc.set_quality(2)
        pcm = w.readframes(w.getnframes())
    return enc.encode(pcm) + enc.flush()


def main():
    ap = argparse.ArgumentParser(description="Tạo audio VOICEVOX cho từ vựng + câu ví dụ.")
    ap.add_argument("--generate", action="store_true", help="Tạo mp3. Không có cờ này thì chỉ kiểm tra.")
    ap.add_argument("--out", type=Path, default=BASE_DIR / "media" / "vocab_audio")
    ap.add_argument("--limit", type=int, help="Chỉ xử lý N từ đầu (thử nhanh).")
    ap.add_argument("--settings", default="config.settings.supabase", help="DJANGO_SETTINGS_MODULE.")
    args = ap.parse_args()

    try:
        say(DIM, "ENGINE", f"VOICEVOX {urllib.request.urlopen(ENGINE + '/version', timeout=5).read().decode()}")
    except OSError:
        say(RED, "LỖI", f"Không gọi được VOICEVOX ở {ENGINE} — mở VOICEVOX rồi chạy lại.")
        sys.exit(1)
    if args.generate:
        try:
            import lameenc  # noqa: F401
        except ImportError:
            say(RED, "LỖI", r"Thiếu lameenc: .venv\Scripts\pip install lameenc")
            sys.exit(1)

    setup_django(args.settings)
    from apps.vocabulary.audio import base_form, is_dirty, phonetic, query_kana, speak_text, word_candidates
    from django.db.models import Prefetch

    from apps.vocabulary.models import ExampleSentence, Vocabulary

    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    # tên file -> sha1(giọng|câu): câu trên DB đổi thì tạo lại, giống thì bỏ qua.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    def make(name, text):
        digest = hashlib.sha1(f"{SPEAKER}|{text}".encode()).hexdigest()
        if manifest.get(name) == digest and (args.out / name).exists():
            return False
        q = audio_query(text)
        (args.out / name).write_bytes(to_mp3(_post("/synthesis", {"speaker": SPEAKER}, q)))
        manifest[name] = digest
        return True

    # .only(): chạy được cả khi DB chưa có cột audio_url mới.
    words = (Vocabulary.objects.only("id", "word", "reading").order_by("id")
             .prefetch_related(Prefetch("examples", ExampleSentence.objects.only("id", "vocabulary_id", "sentence_jp"))))
    if args.limit:
        words = words[: args.limit]
    report, made, skipped = [], 0, 0
    try:
        for i, v in enumerate(words, 1):
            reading = base_form(v.reading)
            heard = []
            for text in word_candidates(v.word):
                heard.append(query_kana(audio_query(text)))
                if phonetic(heard[-1]) == phonetic(reading):
                    break
            else:  # đọc chữ Hán cho trọng âm tự nhiên; engine hiểu sai thì đọc từ kana
                report.append(["reading_mismatch", v.id, v.word, v.reading, heard[0]])
                text = reading
            if args.generate:
                made_now = make(f"w{v.id}.mp3", text)
                made, skipped = made + made_now, skipped + (not made_now)
            for e in v.examples.all():
                if is_dirty(e.sentence_jp):
                    report.append(["dirty_example", e.id, v.word, e.sentence_jp, ""])
                elif args.generate:
                    made_now = make(f"e{e.id}.mp3", speak_text(e.sentence_jp))
                    made, skipped = made + made_now, skipped + (not made_now)
            if i % 100 == 0:
                say(DIM, "…", f"{i} từ (tạo {made}, bỏ qua {skipped}, cần soát {len(report)})")
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    finally:  # Ctrl+C giữa chừng vẫn giữ manifest để lần sau chạy tiếp
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report_path = args.out / "audio_report.csv"
    with report_path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([["issue", "id", "word", "reading_or_sentence", "engine_kana"], *report])
    if args.generate:
        say(GREEN, "XONG", f"tạo {made} file, bỏ qua {skipped} file không đổi → {args.out}")
    say(YELLOW if report else GREEN, "SOÁT", f"{len(report)} dòng → {report_path}")


if __name__ == "__main__":
    main()
