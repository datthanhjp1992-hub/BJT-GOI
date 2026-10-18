"""
Tạo audio NGHĨA TIẾNG VIỆT của từ vựng bằng VieNeu-TTS (giọng Ngọc Huyền) — 2 bước, 2 môi trường:

    # 1. xuất nghĩa đã làm sạch từ DB (venv của BJT-GOI, chỉ ĐỌC database)
    .venv\\Scripts\\python.exe scripts/generate_meaning_audio.py export

    # 2. tạo mp3 trên GPU (venv của VieNeu-TTS; chạy lại thì bỏ qua file không đổi)
    ..\\VieNeu-TTS\\.venv\\Scripts\\python.exe scripts/generate_meaning_audio.py generate

Ra media/meaning_audio/m<id>.mp3 (+ meanings.json, manifest.json).
Bước 2 cần: cd ..\\VieNeu-TTS && uv pip install lameenc
Upload + ghi link vào DB là bước riêng (chưa làm).
"""
import argparse
import hashlib
import json
import re
import sys
import time

from _vocab_common import BASE_DIR, DIM, GREEN, RED, YELLOW, say, setup_django

OUT = BASE_DIR / "media" / "meaning_audio"
VOICE = "Ngọc Huyền"  # Dat chọn sau pilot 18/10/2026 (so với Adam bựa, Mai Anh)
MP3_KBPS = 48
_JP = re.compile(r"[぀-ヿ一-鿿]")


def speak_text(meaning):
    """Phần đọc thành tiếng: bỏ (ghi chú), bỏ đuôi 'VD: / Trái nghĩa: / Khác với / Lưu ý:' (thường kèm chữ Nhật)."""
    s = re.sub(r"\s*[(（][^)）]*[)）]", "", meaning)
    s = re.split(r"\.?\s*(?:VD:|Trái nghĩa:|Khác với|Lưu ý:)", s)[0]
    s = re.sub(r"\s*/\s*", ", ", s)
    s = re.sub(r"\s+([,;.])", r"\1", re.sub(r"\s+", " ", s))
    return s.strip(" ,;.")


assert speak_text("Điều khoản, quy ước (của hợp đồng, dịch vụ)") == "Điều khoản, quy ước"
assert speak_text("Đôn đốc, thúc giục. VD: 督促状 – giấy đòi nợ") == "Đôn đốc, thúc giục"
assert speak_text("Phê duyệt (cấp trên phê duyệt). Khác với 決済 – thanh toán") == "Phê duyệt"
assert speak_text("Đưa vào, nhúng/tích hợp") == "Đưa vào, nhúng, tích hợp"


def export(settings):
    setup_django(settings)
    from apps.vocabulary.models import Vocabulary

    rows, bad = [], []
    for pk, word, meaning in Vocabulary.objects.order_by("id").values_list("id", "word", "meaning_vi"):
        text = speak_text(meaning)
        if not text or _JP.search(text):
            bad.append((pk, word, meaning))
        else:
            rows.append({"id": pk, "word": word, "text": text})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "meanings.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    say(GREEN, "XONG", f"{len(rows)} nghĩa → {OUT / 'meanings.json'}")
    for pk, word, meaning in bad:
        say(YELLOW, "BỎ QUA", f"#{pk} {word}: {meaning!r} — còn chữ Nhật hoặc rỗng, sửa dữ liệu trước")


def to_mp3(audio, rate):
    import lameenc
    import numpy as np

    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    enc = lameenc.Encoder()
    enc.set_bit_rate(MP3_KBPS)
    enc.set_in_sample_rate(rate)
    enc.set_channels(1)
    enc.set_quality(2)
    return enc.encode(pcm) + enc.flush()


def generate(limit):
    try:
        import lameenc  # noqa: F401
        from vieneu import Vieneu
    except ImportError as e:
        say(RED, "LỖI", f"{e} — chạy bằng python của VieNeu-TTS, và: uv pip install lameenc")
        sys.exit(1)

    rows = json.loads((OUT / "meanings.json").read_text(encoding="utf-8"))[:limit]
    manifest_path = OUT / "manifest.json"
    # tên file -> sha1(giọng|câu): nghĩa trên DB đổi thì tạo lại, giống thì bỏ qua.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    tts = Vieneu()
    made = skipped = 0
    t0 = time.time()
    try:
        for i, r in enumerate(rows, 1):
            name = f"m{r['id']}.mp3"
            digest = hashlib.sha1(f"{VOICE}|{r['text']}".encode()).hexdigest()
            if manifest.get(name) == digest and (OUT / name).exists():
                skipped += 1
                continue
            (OUT / name).write_bytes(to_mp3(tts.infer(r["text"], voice=VOICE), 48000))  # VieNeu v3 ra 48 kHz
            manifest[name] = digest
            made += 1
            if i % 100 == 0:
                say(DIM, "…", f"{i}/{len(rows)} (tạo {made}, bỏ qua {skipped}, {time.time() - t0:.0f}s)")
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    finally:  # Ctrl+C giữa chừng vẫn giữ manifest để lần sau chạy tiếp
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    say(GREEN, "XONG", f"tạo {made}, bỏ qua {skipped} file không đổi, {time.time() - t0:.0f}s → {OUT}")


def main():
    ap = argparse.ArgumentParser(description="Tạo audio nghĩa tiếng Việt bằng VieNeu-TTS.")
    ap.add_argument("step", choices=["export", "generate"])
    ap.add_argument("--limit", type=int, help="Chỉ tạo N nghĩa đầu (thử nhanh).")
    ap.add_argument("--settings", default="config.settings.supabase", help="DJANGO_SETTINGS_MODULE.")
    args = ap.parse_args()
    export(args.settings) if args.step == "export" else generate(args.limit)


if __name__ == "__main__":
    main()
