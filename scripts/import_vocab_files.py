"""
Nhập một hoặc nhiều file từ vựng (CSV/Excel theo mẫu "từ vựng đầy đủ") lên Supabase — MỘT lệnh
cho cả chuỗi vẫn làm tay:

    1. scripts/upload_vocab.py           tạo từ mới / thêm topic + câu ví dụ cho từ đã có
    2. scripts/upload_han_viet.py        ghi cột part_of_speech (loại từ) từ file
    3. scripts/generate_vocab_audio.py   audio tiếng Nhật VOICEVOX (tự bật engine nếu chưa chạy)
       scripts/upload_vocab_audio.py     upload + ghi audio_url
    4. scripts/generate_meaning_audio.py audio nghĩa tiếng Việt VieNeu (export → generate)
       scripts/upload_vocab_audio.py media/meaning_audio

    # chạy thử — bước 1 + 2 ở chế độ xem trước, KHÔNG ghi gì (mặc định)
    .venv\\Scripts\\python.exe scripts/import_vocab_files.py docs/data/vocab_bjt/tu_vung_600_thaolejp.csv docs/data/vocab_bjt/cum_tu_co_dinh_thaolejp.csv

    # ghi thật + tạo/upload audio
    .venv\\Scripts\\python.exe scripts/import_vocab_files.py <file...> --apply --as-user dat

    # ghi thật nhưng bỏ phần audio (vd máy không có VOICEVOX / VieNeu)
    .venv\\Scripts\\python.exe scripts/import_vocab_files.py <file...> --apply --as-user dat --no-audio

Chạy lại cùng file là an toàn: các script con đều bỏ qua phần đã có (từ, câu ví dụ, file audio không đổi).
Bước nào lỗi thì dừng ngay, không chạy bước sau.
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from _vocab_common import BASE_DIR, DIM, GREEN, RED, YELLOW, say

PY = sys.executable
VIENEU_PY = BASE_DIR.parent / "VieNeu-TTS" / ".venv" / "Scripts" / "python.exe"
VOICEVOX_EXE = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "VOICEVOX" / "vv-engine" / "run.exe"
ENGINE = "http://127.0.0.1:50021"


def plan(files, apply, as_user, audio):
    """[(tên bước, lệnh)] theo thứ tự chạy. Chạy thử chỉ có bước 1 + 2 (audio cần dữ liệu đã ghi)."""
    tail = ["--apply"] + (["--as-user", as_user] if as_user else []) if apply else []
    steps = []
    for f in files:
        steps.append((f"Từ vựng: {Path(f).name}", [PY, "scripts/upload_vocab.py", f, *tail]))
        steps.append((f"Loại từ: {Path(f).name}",
                      [PY, "scripts/upload_han_viet.py", f, "--column", "part_of_speech", *tail]))
    if apply and audio:
        steps += [
            ("Audio tiếng Nhật: tạo", [PY, "scripts/generate_vocab_audio.py", "--generate"]),
            ("Audio tiếng Nhật: upload", [PY, "scripts/upload_vocab_audio.py", *tail]),
            ("Audio nghĩa: xuất nghĩa", [PY, "scripts/generate_meaning_audio.py", "export"]),
            ("Audio nghĩa: tạo (VieNeu)", [str(VIENEU_PY), "scripts/generate_meaning_audio.py", "generate"]),
            ("Audio nghĩa: upload", [PY, "scripts/upload_vocab_audio.py", "media/meaning_audio", *tail]),
        ]
    return steps


_dry = plan(["a.csv"], False, "dat", True)
assert [s[1][1:] for s in _dry] == [["scripts/upload_vocab.py", "a.csv"],
                                    ["scripts/upload_han_viet.py", "a.csv", "--column", "part_of_speech"]]
_real = plan(["a.csv", "b.csv"], True, "dat", True)
assert len(_real) == 9 and all(s[1][-3:] == ["--apply", "--as-user", "dat"] for s in _real[:4])
assert len(plan(["a.csv"], True, None, False)) == 2 and plan(["a.csv"], True, None, False)[0][1][-1] == "--apply"


def engine_up():
    try:
        urllib.request.urlopen(ENGINE + "/version", timeout=3)
        return True
    except OSError:
        return False


def start_voicevox():
    """Bật VOICEVOX engine nếu chưa chạy; trả về process để tắt khi xong (None nếu đã chạy sẵn)."""
    if engine_up():
        return None
    if not VOICEVOX_EXE.exists():
        say(RED, "LỖI", f"Không thấy VOICEVOX ở {VOICEVOX_EXE} — mở VOICEVOX rồi chạy lại, hoặc thêm --no-audio.")
        sys.exit(1)
    say(DIM, "ENGINE", "Đang bật VOICEVOX…")
    proc = subprocess.Popen([str(VOICEVOX_EXE), "--host", "127.0.0.1", "--port", "50021"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(90):
        if engine_up():
            return proc
        time.sleep(1)
    proc.terminate()
    say(RED, "LỖI", "VOICEVOX không lên sau 90 giây.")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Nhập file từ vựng lên Supabase + tạo/upload audio.")
    ap.add_argument("files", nargs="+", help="File .csv / .xlsx theo mẫu 'từ vựng đầy đủ'.")
    ap.add_argument("--apply", action="store_true", help="Ghi thật. Không có cờ này thì chỉ chạy thử bước 1 + 2.")
    ap.add_argument("--as-user", metavar="USERNAME", help="Ghi created_by/updated_by là user này (vd dat).")
    ap.add_argument("--no-audio", action="store_true", help="Bỏ phần tạo + upload audio.")
    args = ap.parse_args()

    missing = [f for f in args.files if not Path(f).exists()]
    if missing:
        say(RED, "LỖI", f"Không thấy file: {', '.join(missing)}")
        sys.exit(1)
    audio = args.apply and not args.no_audio
    if audio and not VIENEU_PY.exists():
        say(RED, "LỖI", f"Không thấy VieNeu-TTS ở {VIENEU_PY} — thêm --no-audio hoặc cài VieNeu trước.")
        sys.exit(1)

    say(YELLOW if args.apply else GREEN, "MODE", "GHI THẬT" if args.apply else "CHẠY THỬ (không ghi gì)")
    engine = start_voicevox() if audio else None
    try:
        steps = plan(args.files, args.apply, args.as_user, audio)
        for i, (name, cmd) in enumerate(steps, 1):
            print()
            say(YELLOW, f"[{i}/{len(steps)}]", name)
            if subprocess.run(cmd, cwd=BASE_DIR).returncode != 0:
                say(RED, "DỪNG", f"Bước '{name}' lỗi — sửa rồi chạy lại (các bước đã xong sẽ được bỏ qua).")
                sys.exit(1)
    finally:
        if engine:
            engine.terminate()
    print()
    say(GREEN, "XONG", "Đã ghi thật." if args.apply else "Chạy thử xong. Thêm --apply --as-user dat để ghi thật.")


if __name__ == "__main__":
    main()
