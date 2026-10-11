"""
Hàm dùng chung cho các script đẩy từ vựng lên Supabase
(scripts/import_bjt_topics.py, scripts/upload_vocab.py).

- Khoá so khớp chữ/cách đọc, bỏ qua các quy ước đang có trên DB: hậu tố
  （する）, dấu "..." ở đầu, katakana/hiragana trong cách đọc.
- Topic hàng kana (a-line, ka-line, ...) theo chữ đầu của cách đọc — đúng cách
  dữ liệu hiện tại được gán: が→か行, ぱ→は行, katakana quy về hiragana.
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    GREEN = RED = YELLOW = DIM = RESET = ""

# Chữ đầu của cách đọc → slug topic hàng kana đang có trên DB.
KANA_LINE = dict(zip(
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん",
    "a i u e o ka ki ku ke ko sa shi su se so ta chi tsu te to na ni nu ne no "
    "ha hi fu he ho ma mi mu me mo ya yu yo ra ri ru re ro wa wo n".split(),
))
# Chữ nhỏ / có dấu → chữ gốc.
KANA_BASE = dict(zip(
    "ぁぃぅぇぉがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽゃゅょっゎゔ",
    "あいうえおかきくけこさしすせそたちつてとはひふへほはひふへほやゆよつわう",
))

# Quy ước trên DB: động từ する ghi kèm hậu tố 協働（する）/ きょうどう（する）.
SURU = re.compile(r"\((?:を)?する\)$")
ALT_SEP = re.compile(r"[、・=]")


def say(color, tag, msg):
    print(f"{color}{tag}{RESET} {msg}")


def norm(text) -> str:
    """NFKC, bỏ khoảng trắng, gom các kiểu dấu sóng về một."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    for ch in "〜～":
        text = text.replace(ch, "~")
    return "".join(text.split())


def to_hiragana(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def wkey(word) -> str:
    """Khoá so khớp của chữ: bỏ hậu tố (する), dấu .../~ ở đầu, ?。! ở cuối và
    dấu ngoặc — DB ghi （時間が）押す /（じかんが）おす, file nguồn ghi じかんがおす."""
    text = SURU.sub("", norm(word)).lstrip(".~").rstrip("?!。")
    return text.replace("(", "").replace(")", "")


def rkey(reading) -> str:
    """Khoá so khớp của cách đọc: như wkey + katakana → hiragana
    (DB lưu アクセス lẫn あくせす, hai cách coi là một)."""
    return to_hiragana(wkey(reading))


def alt_parts(word) -> set[str]:
    """Các dạng thay thế trong một ô: 'お手数ですが、お手数をかけますが' → 2 khoá."""
    text = norm(word)
    if not ALT_SEP.search(text):
        return set()
    return {k for k in (wkey(p) for p in ALT_SEP.split(text)) if len(k) >= 2}


def kana_line_slug(reading) -> str | None:
    for ch in to_hiragana(str(reading or "")):
        ch = KANA_BASE.get(ch, ch)
        if ch in KANA_LINE:
            return f"{KANA_LINE[ch]}-line"
    return None


def setup_django(settings_module: str):
    """django.setup() rồi in DB đang trỏ tới, để không lỡ tay ghi nhầm môi trường."""
    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module
    import django

    django.setup()
    from django.db import connection

    with connection.cursor() as c:
        c.execute("select current_database(), coalesce(host(inet_server_addr()), 'local')")
        dbname, host = c.fetchone()
    say(DIM, "DB", f"{settings_module} → database={dbname} server={host}")


def act_as(username: str | None):
    """Cho AuditableModel.save() ghi created_by/updated_by là user này."""
    from apps.core import middleware

    if not username:
        middleware._thread_locals.user = None
        return
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(username=username).first()
    if user is None:
        say(RED, "LỖI", f"Không có user '{username}'.")
        sys.exit(1)
    middleware._thread_locals.user = user


class DryRun(Exception):
    """Ném ra cuối transaction để rollback khi chạy thử."""
